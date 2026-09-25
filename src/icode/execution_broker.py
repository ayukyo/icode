"""R2 策略命令的宿主侧启动与回收，不代替 OS 文件/网络隔离。"""

from __future__ import annotations

import errno
import os
import selectors
import signal
import subprocess
import sys
import time
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
    argv: list[str], *, cwd: Path, policy: SandboxPolicy, timeout: int,
    git_status: bool = False, output_limit_bytes: int | None = None,
) -> ExecutionResult:
    """执行已由原生后端包装的命令；超时/超量时终止整组。"""
    if os.name != "posix":
        return ExecutionResult(None, "", 0, "unsupported_platform", False, False, None)

    output_limit = policy.output_limit_bytes
    if output_limit_bytes is not None:
        try:
            requested_output_limit = int(output_limit_bytes)
        except (TypeError, ValueError, OverflowError):
            return ExecutionResult(None, "", 0, "invalid_output_limit", False, True, None)
        if requested_output_limit < 1:
            return ExecutionResult(None, "", 0, "invalid_output_limit", False, True, None)
        output_limit = min(output_limit, requested_output_limit)

    deadline = time.monotonic() + min(max(1, int(timeout)), policy.wall_timeout_seconds)
    try:
        process = subprocess.Popen(  # noqa: S603 - argv 经原生策略包装且 shell=False
            argv, cwd=str(cwd),
            env=_policy_environment(policy.workspace_root, git_status=git_status),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            shell=False, start_new_session=True,
        )
    except (OSError, ValueError):
        return ExecutionResult(None, "", 0, "launch_failed", False, True, None)

    chunks: list[bytes] = []
    output_bytes = 0
    error: str | None = None
    selector = selectors.DefaultSelector()
    try:
        assert process.stdout is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = "timeout"
                break
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
