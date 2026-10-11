"""R2 策略命令的宿主侧启动与回收，不代替 OS 文件/网络隔离。"""

from __future__ import annotations

import errno
import math
import os
import selectors
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .sandbox_policy import SandboxPolicy

if TYPE_CHECKING:
    from .linux_helper_object import LinuxHelperObject

_READ_CHUNK_BYTES = 64 * 1024
_CLEANUP_TIMEOUT_SECONDS = 1
# Separate manager transport limits never consume the payload output budget.
_MANAGER_STDERR_LIMIT_BYTES = 64 * 1024
_MANAGER_STDOUT_LIMIT_BYTES = 8192
_MANAGER_QUERY_TIMEOUT_SECONDS = 0.4
_RESOURCE_CONFIGURE_TIMEOUT_SECONDS = 2


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
    violation_receipt: dict[str, object] | None = None
    violation_observer_status: str | None = None
    resource_receipt: dict[str, object] | None = None
    scope_cleanup_ok: bool | None = None
    payload_started: bool | None = None


def _policy_environment(
    root: Path, *, git_status: bool = False, verification_cache_root: Path | None = None,
) -> dict[str, str]:
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
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
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
    if verification_cache_root is not None:
        if git_status:
            raise ValueError("Git queries do not accept verification caches")
        cache = verification_cache_root
        status = cache.lstat()
        if (
            cache.parent != root
            or not cache.name.startswith(".icode-verification-")
            or cache.resolve(strict=True) != cache
            or not stat.S_ISDIR(status.st_mode)
        ):
            raise ValueError("invalid host verification cache")
        environment.update(
            HOME=str(cache / "home"), USERPROFILE=str(cache / "home"),
            XDG_CONFIG_HOME=str(cache / "config"), APPDATA=str(cache / "config"),
            LOCALAPPDATA=str(cache / "local"),
            TMPDIR=str(cache / "tmp"), TEMP=str(cache / "tmp"), TMP=str(cache / "tmp"),
            GOCACHE=str(cache / "cache"), GOMODCACHE=str(cache / "mod"),
            GOPATH=str(cache / "gopath"), GOENV="off", GOTOOLCHAIN="local",
            GOPROXY="off", GOFLAGS="", GOMAXPROCS="1",
        )
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
    if getattr(argv, "helper_object", None) is not None:
        return ExecutionResult(None, "", 0, "invalid_handoff", False, True, None,
                               payload_started=False)
    return _execute_policy_command(
        argv, cwd=cwd, policy=policy, timeout=timeout,
        git_status=git_status, output_limit_bytes=output_limit_bytes,
        launch_cwd=getattr(argv, "cwd", None),
        pass_fds=getattr(argv, "pass_fds", ()),
    )


class _LinuxViolationCommandWrapper(Protocol):
    def __call__(
        self, argv: list[str], control_socket: socket.socket, *,
        helper_object: LinuxHelperObject,
    ) -> list[str]: ...


class _LinuxResourceCommandWrapper(Protocol):
    def __call__(
        self, argv: list[str], control_socket: socket.socket,
        resource_socket: socket.socket, unit: str, *, helper_object: LinuxHelperObject,
    ) -> list[str]: ...


def execute_linux_violation_observed_command(
    argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
    timeout: int | float, output_limit_bytes: int | None = None,
    command_wrapper: _LinuxViolationCommandWrapper,
) -> ExecutionResult:
    return _execute_linux_observed_command(
        argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
        output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
        resource_mode=False, helper_object_mode=True,
    )


def execute_linux_resource_observed_command(
    argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
    timeout: int | float, output_limit_bytes: int | None = None,
    command_wrapper: _LinuxResourceCommandWrapper,
    verification_cache_root: Path | None = None,
) -> ExecutionResult:
    """Actual policy-command quota chain; not an automatic-mode support grant."""
    return _execute_linux_observed_command(
        argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
        output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
        resource_mode=True, helper_object_mode=True,
        verification_cache_root=verification_cache_root,
    )


def _check_held_helper_launch(wrapped, owner, *, policy, helper_index,
                            scope_prefix, channel_fds, launch_fds, argv_snapshot):
    from .isolation import PreparedCommand
    from .linux_helper_object import LinuxHelperObject
    if (type(owner) is not LinuxHelperObject or type(wrapped) is not PreparedCommand
            or wrapped.helper_object is not owner or tuple(wrapped) != argv_snapshot):
        raise ValueError("invalid helper object binding")
    helper_fd = owner.fileno()  # regular and same dev/ino; dead/reused fails here.
    if type(helper_fd) is not int or helper_fd < 3:
        raise ValueError("invalid helper descriptor")
    if (type(helper_index) is not int or helper_index < 0
            or helper_index >= len(wrapped)
            or tuple(wrapped[:helper_index]) != scope_prefix
            or wrapped[helper_index] != f"/proc/self/fd/{helper_fd}"):
        raise ValueError("invalid helper program position")
    inner = wrapped[helper_index:]
    separator = inner.index("--")
    flags = inner[1:separator]
    roles = [helper_fd, *channel_fds]
    for flag, fd in zip(("--violation-control-fd", "--resource-control-fd"), channel_fds, strict=False):
        if flags.count(flag) != 1 or flags[flags.index(flag) + 1] != str(fd):
            raise ValueError("invalid channel role")
    if len(channel_fds) == 1 and "--resource-control-fd" in flags:
        raise ValueError("unexpected resource role")
    if "--workspace-fd" in flags:
        raise ValueError("unexpected Reviewer role")
    if "--workspace-object-fd" in flags:
        if flags.count("--workspace-object-fd") != 1:
            raise ValueError("duplicate workspace role")
        index = flags.index("--workspace-object-fd")
        raw_fd, raw_dev, raw_ino = flags[index + 1:index + 4]
        workspace_fd, device, inode = int(raw_fd), int(raw_dev), int(raw_ino)
        if (str(workspace_fd), str(device), str(inode)) != (raw_fd, raw_dev, raw_ino) or workspace_fd < 3:
            raise ValueError("invalid workspace role")
        pinned, current = os.fstat(workspace_fd), policy.workspace_root.lstat()
        if (not stat.S_ISDIR(pinned.st_mode) or not stat.S_ISDIR(current.st_mode)
                or (pinned.st_dev, pinned.st_ino) != (device, inode)
                or (current.st_dev, current.st_ino) != (device, inode)):
            raise ValueError("invalid workspace identity")
        roles.append(workspace_fd)
    expected = tuple(roles)
    if (type(wrapped.pass_fds) is not tuple or type(launch_fds) is not tuple
            or any(type(fd) is not int or fd < 3 for fd in wrapped.pass_fds)
            or any(type(fd) is not int or fd < 3 for fd in launch_fds)
            or len(set(expected)) != len(expected)
            or len(set(launch_fds)) != len(launch_fds)
            or set(launch_fds) != set(expected)
            or set(wrapped.pass_fds) != set(expected) - set(channel_fds)
            or len(set(wrapped.pass_fds)) != len(wrapped.pass_fds)):
        raise ValueError("invalid helper descriptor roles")


def _execute_linux_helper_observed_candidate(
    argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
    timeout: int | float, resource_mode: bool,
    output_limit_bytes: int | None = None,
    command_wrapper: Callable[..., list[str]],
    verification_cache_root: Path | None = None,
) -> ExecutionResult:
    return _execute_linux_observed_command(
        argv, cwd=cwd, sandbox=sandbox, policy=policy, timeout=timeout,
        output_limit_bytes=output_limit_bytes, command_wrapper=command_wrapper,
        resource_mode=resource_mode, verification_cache_root=verification_cache_root,
        helper_object_mode=True,
    )


def _execute_linux_observed_command(
    argv: list[str], *, cwd: Path, sandbox: object, policy: SandboxPolicy,
    timeout: int | float, output_limit_bytes: int | None,
    command_wrapper: Callable[..., list[str]], resource_mode: bool,
    verification_cache_root: Path | None = None,
    helper_object_mode: bool = False,
) -> ExecutionResult:
    """Run a Linux deny-only command with a pre-exec USER_NOTIF observer.

    This is used only when the real Landlock helper is explicitly selected.
    The notification broker always answers EPERM; an absent or failed observer
    prevents payload execution and never degrades to an unobserved command.
    """
    owner = None
    try:
        if type(helper_object_mode) is not bool:
            return ExecutionResult(None, "", 0, "invalid_violation_scope", False, True, None)
        if not sys.platform.startswith("linux"):
            return ExecutionResult(None, "", 0, "unsupported_platform", False, False, None)

        from .isolation import LandlockSandbox
        from .linux_seccomp_notify import (
            LinuxSeccompViolationMonitor,
            create_seccomp_listener_handoff_channel,
        )
        from .sandbox_policy import NetworkMode
        from .linux_task_resource import _select_cleanup_error

        if (
            not isinstance(sandbox, LandlockSandbox)
            or not isinstance(policy, SandboxPolicy)
            or policy.network_mode is not NetworkMode.DENY
            or policy.allowed_domains
        ):
            return ExecutionResult(None, "", 0, "invalid_violation_scope", False, True, None)

        if verification_cache_root is not None:
            try:
                if not resource_mode:
                    raise ValueError("verification requires resource scope")
                _policy_environment(policy.workspace_root, verification_cache_root=verification_cache_root)
                if (
                    not any(verification_cache_root.is_relative_to(root) for root in policy.write_roots)
                    or any(verification_cache_root.is_relative_to(root) or root.is_relative_to(verification_cache_root)
                           for root in (*policy.deny_read_roots, *policy.deny_write_roots, *policy.protected_paths))
                ):
                    raise ValueError("verification cache is not within the approved scope")
            except (OSError, RuntimeError, TypeError, ValueError):
                return ExecutionResult(None, "", 0, "invalid_verification_cache", False, True, None,
                                       payload_started=False)

        host_control: socket.socket | None = None
        sender_control: socket.socket | None = None
        monitor: LinuxSeccompViolationMonitor | None = None
        resource_host: socket.socket | None = None
        resource_sender: socket.socket | None = None
        resource = task_scope = None
        scope_cleanup_ok: bool | None = None
        launch_start = 0.0
        monitor_closed = resource_closed = components_drained = False
        endpoint_attempts: set[int] = set()
        endpoint_cleanup_error: BaseException | None = None
        endpoint_snapshots: dict[int, tuple[int, tuple[int, int, int]]] = {}

        def snapshot_endpoints(*endpoints: socket.socket) -> None:
            if not helper_object_mode:
                return
            for endpoint in endpoints:
                descriptor = endpoint.fileno()
                status = os.fstat(descriptor)
                if type(descriptor) is not int or descriptor < 3 or not stat.S_ISSOCK(status.st_mode):
                    raise ValueError("invalid channel object")
                endpoint_snapshots[id(endpoint)] = (
                    descriptor, (status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode)),
                )

        def check_endpoint(endpoint: socket.socket, *, allow_closed: bool = False) -> bool:
            from .linux_helper_object import LinuxHelperObjectError
            snapshot = endpoint_snapshots.get(id(endpoint))
            if snapshot is None:
                raise LinuxHelperObjectError()
            descriptor, identity = snapshot
            current = endpoint.fileno()
            if current == -1 and allow_closed:
                try:
                    os.fstat(descriptor)
                except OSError as error:
                    if error.errno == errno.EBADF:
                        return False
                    raise
                # A detached live descriptor is not evidence of socket close.
                raise LinuxHelperObjectError()
            if type(current) is not int or current != descriptor:
                raise LinuxHelperObjectError()
            status = os.fstat(descriptor)
            if (not stat.S_ISSOCK(status.st_mode)
                    or (status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode)) != identity):
                raise LinuxHelperObjectError()
            return True

        def manager_query(command: list[str], environment: dict[str, str], deadline: float) -> bytes:
            from .linux_task_scope import LinuxTaskScopeError
            remaining = min(_MANAGER_QUERY_TIMEOUT_SECONDS, deadline - time.monotonic())
            if remaining <= 0:
                raise LinuxTaskScopeError()
            query_policy = replace(policy, output_limit_bytes=_MANAGER_STDOUT_LIMIT_BYTES, wall_timeout_seconds=1)
            answer = _execute_policy_command(command, cwd=working_directory, policy=query_policy,
                                             timeout=remaining, output_limit_bytes=_MANAGER_STDOUT_LIMIT_BYTES,
                                             launch_env=environment, manager_stderr=True)
            if answer.error is not None or answer.exit_code != 0:
                raise LinuxTaskScopeError()
            return answer.raw_output

        def drain_components(cleanup_error):
            nonlocal monitor_closed, resource_closed, components_drained
            if not components_drained:
                components_drained = True  # Drain once, even if close raises.
                for operation in ("resource_wait", "resource_close", "monitor_close"):
                    try:
                        if operation == "resource_wait" and resource is not None:
                            resource.wait(timeout_seconds=0.2)
                        elif operation == "resource_close" and resource is not None:
                            resource_closed = resource.close()
                        elif operation == "monitor_close" and monitor is not None:
                            monitor_closed = monitor.close()
                    except BaseException as error:
                        cleanup_error = _select_cleanup_error(cleanup_error, error)
            return cleanup_error

        def close_endpoint(endpoint: socket.socket) -> None:
            nonlocal endpoint_cleanup_error
            if not helper_object_mode:
                endpoint.close()
                return
            identity = id(endpoint)
            if identity in endpoint_attempts:
                return
            # Relinquish retry responsibility before an ambiguous close.
            endpoint_attempts.add(identity)
            try:
                live = check_endpoint(endpoint, allow_closed=True)
                if not live:
                    return
                endpoint.close()
            except BaseException as error:
                # Disarm both stale identities and ambiguous close outcomes.
                # Detach never closes a numeric FD or supplies cleanup credit;
                # it prevents __del__ from making an unsafe second close.
                selected = error
                try:
                    socket.socket.detach(endpoint)
                except BaseException as cleanup_error:
                    selected = _select_cleanup_error(error, cleanup_error)
                endpoint_cleanup_error = _select_cleanup_error(endpoint_cleanup_error, selected)
                if selected is not error:
                    raise selected
                raise

        def close_endpoints() -> None:
            active_exception = sys.exc_info()[1]
            cleanup_error = drain_components(endpoint_cleanup_error if helper_object_mode else active_exception)
            for endpoint in (resource_sender, resource_host, sender_control, host_control):
                if endpoint is None:
                    continue
                try:
                    close_endpoint(endpoint)
                except OSError as error:
                    if helper_object_mode:
                        cleanup_error = _select_cleanup_error(cleanup_error, error)
                except BaseException as error:
                    cleanup_error = _select_cleanup_error(cleanup_error, error)
            if task_scope is not None:
                try:
                    task_scope.close()
                    if helper_object_mode and task_scope.cleanup_state != "confirmed":
                        from .linux_task_scope import LinuxTaskScopeError
                        raise LinuxTaskScopeError()
                except BaseException as error:
                    cleanup_error = _select_cleanup_error(cleanup_error, error)
            if helper_object_mode:
                if cleanup_error is None:
                    return
                # Signals keep their exact original object; an ordinary body exception
                # must never hide an independent unknown cleanup and yield cleanup_ok.
                if active_exception is not None and not isinstance(active_exception, Exception):
                    return  # Existing unwinding propagates the original signal.
                if not isinstance(cleanup_error, Exception):
                    raise cleanup_error
                from .linux_helper_object import LinuxHelperObjectError
                raise LinuxHelperObjectError() from None
            if cleanup_error is not None and cleanup_error is not active_exception:
                raise cleanup_error
        try:
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
            if helper_object_mode:
                from .linux_helper_object import open_linux_helper_object
                if sandbox.manifest is None:
                    raise RuntimeError("helper manifest is unavailable")
                owner = open_linux_helper_object(Path(sandbox.helper), Path(sandbox.manifest))
            if resource_mode:
                from .linux_task_scope import LinuxTaskScope
                from .linux_task_resource import create_task_resource_channel
                task_scope = LinuxTaskScope(limit=policy.process_limit, query=manager_query)
                resource_host, resource_sender = create_task_resource_channel()
                snapshot_endpoints(resource_host, resource_sender)
            host_control, sender_control = create_seccomp_listener_handoff_channel()
            snapshot_endpoints(host_control, sender_control)
        except (IndexError, OSError, RuntimeError, TypeError, ValueError):
            close_endpoints()
            return ExecutionResult(
                None, "", 0, "isolation_unavailable" if helper_object_mode else ("resource_setup_failed" if resource_mode else "violation_observer_setup_failed"), False, True, None,
                violation_observer_status="incomplete",
                payload_started=False if resource_mode or helper_object_mode else None,
            )
        except BaseException:
            close_endpoints()
            raise

        try:
            wrapper_keywords = {"helper_object": owner} if helper_object_mode else {}
            if resource_mode:
                assert task_scope is not None and resource_sender is not None and resource_host is not None
                from .linux_task_resource import LinuxTaskResourceReceiver
                helper_command = command_wrapper(argv, sender_control, resource_sender, task_scope.unit, **wrapper_keywords)
                if helper_object_mode:
                    helper_snapshot = tuple(helper_command)
                    helper_metadata = tuple(getattr(helper_command, field, None)
                                            for field in ("pass_fds", "cwd", "helper_object"))
                wrapped = task_scope.wrap(helper_command)
                if helper_object_mode:
                    helper_index = wrapped.index("--") + 1
                    scope_prefix = tuple(wrapped[:helper_index])
                    # Validate the single trusted wrap result, never rewrap
                    # after the environment or before the process launch.
                    flags = ("--expand-environment=no",) if task_scope.version >= 254 else ()
                    expected_prefix = (
                        "/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                        "--no-ask-password", "--description=ICODE task command",
                        f"--unit={task_scope.unit}", "--property=Delegate=pids", *flags, "--",
                    )
                    wrapped_metadata = tuple(getattr(wrapped, field, None)
                                             for field in ("pass_fds", "cwd", "helper_object"))
                    if (scope_prefix != expected_prefix
                            or tuple(wrapped[helper_index:]) != helper_snapshot
                            or wrapped_metadata != helper_metadata):
                        raise ValueError("invalid trusted scope wrapping")
                else:
                    helper_index, scope_prefix = 0, ()

                def configured(deadline: float) -> None:
                    task_scope.configured(min(deadline, launch_start + _RESOURCE_CONFIGURE_TIMEOUT_SECONDS))

                resource = LinuxTaskResourceReceiver(resource_host, unit=task_scope.unit,
                                                     limit=policy.process_limit, on_configured=configured)
            else:
                wrapped = command_wrapper(argv, sender_control, **wrapper_keywords)
                helper_index, scope_prefix = 0, ()
            if not helper_object_mode and getattr(wrapped, "helper_object", None) is not None:
                raise ValueError("unexpected helper binding")
            argv_snapshot = tuple(wrapped)
            # Preserve the borrowed workspace object alongside both private channels.
            # A collision is an invalid launch contract, never silently deduplicated.
            workspace_fds = getattr(wrapped, "pass_fds", ())
            channel_fds = ((sender_control.fileno(), resource_sender.fileno())
                           if resource_sender is not None else (sender_control.fileno(),))
            if (type(workspace_fds) is not tuple
                    or any(type(fd) is not int or fd < 3 for fd in workspace_fds)):
                raise ValueError("invalid workspace descriptors")
            launch_fds = (*workspace_fds, *channel_fds)
            if len(set(launch_fds)) != len(launch_fds):
                raise ValueError("duplicate launch descriptor")
            launch_cwd = getattr(wrapped, "cwd", None)
            def before_spawn():
                # Metadata is frozen with the argv, before environment construction.
                if wrapped.pass_fds != workspace_fds or wrapped.cwd != launch_cwd:
                    raise ValueError("changed helper launch metadata")
                check_endpoint(sender_control)
                if resource_sender is not None:
                    check_endpoint(resource_sender)
                _check_held_helper_launch(wrapped, owner, policy=policy, helper_index=helper_index,
                                         scope_prefix=scope_prefix, channel_fds=channel_fds,
                                         launch_fds=launch_fds, argv_snapshot=argv_snapshot)
            if helper_object_mode:
                before_spawn()
            monitor = LinuxSeccompViolationMonitor(host_control)
        except (IndexError, OSError, RuntimeError, TypeError, ValueError):
            close_endpoints()
            return ExecutionResult(
                None, "", 0, "isolation_unavailable", False, True, None,
                violation_observer_status="incomplete",
                payload_started=False if resource_mode or helper_object_mode else None,
            )
        except BaseException:
            close_endpoints()
            raise

        def start_observer(process: subprocess.Popen[bytes], deadline: float) -> None:
            assert monitor is not None and sender_control is not None
            try:
                close_endpoint(sender_control)
                if resource is not None:
                    assert resource_sender is not None and task_scope is not None
                    close_endpoint(resource_sender)
                    task_scope.bind_process(process.pid)
                    resource.bind_process(process, expected_uid=os.getuid(), expected_gid=os.getgid())
                    resource.start(deadline_monotonic=deadline,
                                   configured_deadline_monotonic=min(deadline, launch_start + _RESOURCE_CONFIGURE_TIMEOUT_SECONDS))
                monitor.bind_process(process)
                monitor.start(deadline_monotonic=deadline)
            except Exception:  # noqa: BLE001 - observer setup failure kills payload.
                monitor.abort()
                if resource_mode:
                    raise

        result: ExecutionResult
        try:
            assert sender_control is not None and monitor is not None
            launch_start = time.monotonic()
            launch_env = None
            if task_scope is not None:
                launch_env = _policy_environment(policy.workspace_root, verification_cache_root=verification_cache_root)
                for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
                    launch_env[key] = task_scope.environment[key]
            result = _execute_policy_command(
                wrapped,
                cwd=working_directory,
                policy=policy,
                timeout=timeout,
                output_limit_bytes=output_limit_bytes,
                pass_fds=launch_fds,
                launch_cwd=launch_cwd,
                on_spawn=start_observer,
                launch_env=launch_env,
                manager_stderr=resource_mode,
                before_spawn=before_spawn if helper_object_mode else None,
            )
            if helper_object_mode and result.error == "invalid_handoff":
                result = replace(result, payload_started=False)
        finally:
            cleanup_error = drain_components(None)
            try:
                if task_scope is not None:
                    scope_cleanup_ok = task_scope.collected(time.monotonic() + 1)
            except BaseException as exception:
                cleanup_error = _select_cleanup_error(cleanup_error, exception)
            finally:
                try:
                    close_endpoints()
                except BaseException as exception:
                    cleanup_error = _select_cleanup_error(cleanup_error, exception)
            if cleanup_error is not None:
                active_exception = sys.exc_info()[1]
                if helper_object_mode and isinstance(active_exception, Exception):
                    from .linux_helper_object import LinuxHelperObjectError
                    if isinstance(cleanup_error, LinuxHelperObjectError):
                        # Unknown owned cleanup must not disappear behind an
                        # ordinary body failure; the original signal still wins.
                        raise cleanup_error
                selected = _select_cleanup_error(active_exception, cleanup_error)
                if selected is not active_exception:
                    raise selected

        assert monitor is not None
        observer_ok = monitor_closed and monitor._started and not monitor.failed
        receipt = monitor.receipt() if observer_ok else None
        error = result.error
        preserved_errors = ("timeout", "output_limit", "cleanup_failed", "invalid_timeout",
                            "invalid_output_limit", "launch_failed")
        candidate_not_started = (helper_object_mode and result.payload_started is False
                                 and error in ("isolation_unavailable", "invalid_handoff"))
        if not observer_ok and error not in preserved_errors and not candidate_not_started:
            error = "violation_observer_failed"
        outcome = replace(result, error=error, violation_receipt=receipt,
                          violation_observer_status="complete" if observer_ok else "incomplete")
        if resource_mode:
            resource_receipt = resource.receipt() if resource is not None else None
            if resource_receipt is not None and not resource_closed:
                resource_receipt = dict(resource_receipt, channel_status="incomplete", terminal=None,
                                        payload_started=None)
            complete = resource_receipt is not None and resource_receipt["channel_status"] == "complete"
            started = resource_receipt["payload_started"] if complete else result.payload_started
            if candidate_not_started:
                started = False
            if outcome.error is None and not complete:
                outcome = replace(outcome, error="resource_channel_failed")
            if outcome.error is None and scope_cleanup_ok is not True:
                outcome = replace(outcome, error="scope_cleanup_failed")
            outcome = replace(outcome, resource_receipt=resource_receipt,
                              scope_cleanup_ok=scope_cleanup_ok, payload_started=started)
            terminal = resource_receipt["terminal"] if complete else None
            if terminal in ("preexec_failed", "cleanup_failed"):
                outcome = replace(outcome, error="resource_setup_failed" if terminal == "preexec_failed"
                                  else "resource_cleanup_failed")
            if started is False or terminal == "cleanup_failed":
                outcome = replace(outcome, output="", raw_output=b"", output_bytes=0)
        return outcome
    finally:
        if owner is not None:
            active_exception = sys.exc_info()[1]
            try:
                owner.close()
            except BaseException as cleanup_error:
                from .linux_task_resource import _select_cleanup_error
                from .linux_helper_object import LinuxHelperObjectError
                if (isinstance(cleanup_error, LinuxHelperObjectError)
                        and isinstance(active_exception, Exception)
                        and not isinstance(active_exception, LinuxHelperObjectError)):
                    selected = cleanup_error
                else:
                    selected = _select_cleanup_error(active_exception, cleanup_error)
                if selected is not active_exception:
                    raise selected


def _execute_policy_command(
    argv: list[str], *, cwd: Path, policy: SandboxPolicy, timeout: int | float,
    git_status: bool = False, output_limit_bytes: int | None = None,
    pass_fds: tuple[int, ...] = (),
    launch_cwd: str | Path | None = None,
    on_spawn: Callable[[subprocess.Popen[bytes], float], None] | None = None,
    launch_env: dict[str, str] | None = None,
    manager_stderr: bool = False,
    before_spawn: Callable[[], None] | None = None,
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
    launch_directory = cwd
    if launch_cwd is not None:
        if not isinstance(launch_cwd, (str, Path)):
            return ExecutionResult(None, "", 0, "invalid_handoff", False, True, None)
        try:
            launch_directory = Path(launch_cwd).resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            return ExecutionResult(None, "", 0, "invalid_handoff", False, True, None)
        if not launch_directory.is_dir():
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
        environment = (launch_env if launch_env is not None else
                       _policy_environment(policy.workspace_root, git_status=git_status))
        launch_options = {"pass_fds": pass_fds} if pass_fds else {}
        if before_spawn is not None:
            try:
                before_spawn()
            except (IndexError, OSError, RuntimeError, TypeError, ValueError):
                return ExecutionResult(None, "", 0, "isolation_unavailable", False, True, None,
                                       violation_observer_status="incomplete", payload_started=False)
        process = subprocess.Popen(  # noqa: S603 - argv 经原生策略包装且 shell=False
            argv, cwd=str(launch_directory),
            env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if manager_stderr else subprocess.STDOUT,
            shell=False, start_new_session=True, **launch_options,
        )
    except (OSError, ValueError):
        return ExecutionResult(None, "", 0, "launch_failed", False, True, None, payload_started=False)

    chunks: list[bytes] = []
    output_bytes = 0
    error: str | None = None
    manager_bytes = 0
    selector: selectors.BaseSelector | None = None
    try:
        # Popen has transferred process/pipe ownership already. Selector
        # creation can fail (for example EMFILE), so it belongs to cleanup too.
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        if on_spawn is not None:
            try:
                on_spawn(process, deadline)
            except Exception:  # noqa: BLE001 - trusted handoff failure denies execution.
                error = "proxy_setup_failed"
        if error is None:
            selector.register(process.stdout, selectors.EVENT_READ, "payload")
            if manager_stderr:
                assert process.stderr is not None
                selector.register(process.stderr, selectors.EVENT_READ, "manager")
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
                    min(_READ_CHUNK_BYTES, (_MANAGER_STDERR_LIMIT_BYTES - manager_bytes + 1)
                        if key.data == "manager" else (output_limit - output_bytes + 1)),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "manager":
                    manager_bytes += len(chunk)
                    if manager_bytes > _MANAGER_STDERR_LIMIT_BYTES:
                        error = "manager_output_limit"
                        break
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
        # Failure in one cleanup must not skip the remaining owned resources;
        # programmer errors and interrupts still propagate after the attempts.
        from .linux_task_resource import _select_cleanup_error
        active_exception = sys.exc_info()[1]
        cleanup_error = active_exception
        try:
            if selector is not None:
                selector.close()
        except BaseException as exception:
            cleanup_error = _select_cleanup_error(cleanup_error, exception)
        try:
            cleanup_ok, cleanup_errno = _stop_group(process)
        except BaseException as exception:
            cleanup_error = _select_cleanup_error(cleanup_error, exception)
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except BaseException as exception:
                cleanup_error = _select_cleanup_error(cleanup_error, exception)
        if cleanup_error is not None and cleanup_error is not active_exception:
            raise cleanup_error

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
    scope_owned = False
    host_control: socket.socket | None = None
    sender_control: socket.socket | None = None
    try:
        # Establish the policy identity before taking ownership; a wrong-scope
        # caller must not close another task's active proxy session.
        scope.validate_policy_identity(policy)
        # Once the identity matches, this candidate owns cleanup even when
        # the lease is already revoked or expired before process launch.
        scope_owned = True
        scope.verify_lease()
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
        if scope_owned:
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
        if scope_owned:
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
