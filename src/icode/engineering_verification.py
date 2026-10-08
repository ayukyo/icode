"""Frozen host-owned engineering checks, not a model tool or quality oracle.

Results describe complete framework-reported observations under an explicit
execution boundary. Project code can forge framework output; an independent
Reviewer and the contract/control-plane checks are still required.
"""

from __future__ import annotations

import hashlib
import io
import contextlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .execution_broker import _policy_environment
from .linux_task_resource import _select_cleanup_error
from .pack_verify import loads_json_value
from .tools.base import IsolationUnavailable, ToolContext
from .workspace_snapshot import WorktreeTreeUnavailable, snapshot_fingerprint, snapshot_workspace

MAX_CHECKS = 16
MAX_PLAN_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PLAN_TIMEOUT_SECONDS = 1800
MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
MAX_ARGV_BYTES = 64 * 1024
MAX_JSON_EVENTS = 32768
_CHECK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_SUMMARY = re.compile(r"(?m)^Ran ([0-9]{1,7}) tests? in [0-9.]+s\r?$\n\r?\n(OK(?: \([^\r\n]+\))?)\r?\n?\Z")
_GO_PREFIX = ("test", "-json", "-count=1", "-p", "1", "-parallel", "1", "-mod=readonly")
_GO_FIELDS = frozenset({"Time", "Action", "Package", "Test", "Elapsed", "Output",
                        "OutputType", "FailedBuild", "Key", "Value", "Path"})


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _text(value: object, *, max_bytes: int = 8192) -> bool:
    if type(value) is not str or "\x00" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= max_bytes
    except UnicodeEncodeError:
        return False


def _executable_identity(path: Path) -> str:
    """Observe one executable, not its whole toolchain or publisher identity."""
    lexical_before = path.lstat()
    resolved = path.resolve(strict=True)
    with _local_descriptor(os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))) as descriptor:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_EXECUTABLE_BYTES:
            raise ValueError("unsupported verification executable")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 64 * 1024):
            total += len(chunk)
            if total > MAX_EXECUTABLE_BYTES:
                raise ValueError("verification executable exceeds bound")
            digest.update(chunk)
        after = os.fstat(descriptor)
        lexical_after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("verification executable changed")
        if (lexical_before.st_dev, lexical_before.st_ino, lexical_before.st_mtime_ns,
                lexical_before.st_ctime_ns) != (lexical_after.st_dev, lexical_after.st_ino,
                                              lexical_after.st_mtime_ns, lexical_after.st_ctime_ns) or path.resolve(strict=True) != resolved:
            raise ValueError("verification executable alias changed")
        return _canonical_digest({"sha256": digest.hexdigest(), "size": total,
                                  "requested_path": str(path), "resolved_path": str(resolved),
                                  "alias_device": lexical_before.st_dev, "alias_inode": lexical_before.st_ino,
                                  "device": before.st_dev, "inode": before.st_ino,
                                  "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns})


@dataclass(frozen=True)
class VerificationCheck:
    check_id: str
    kind: str
    argv: tuple[str, ...]
    adapter: str
    cwd: str = "."
    required: bool = True
    timeout_seconds: int | float = 180
    output_limit_bytes: int = 1024 * 1024
    executable_identity: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.check_id) is not str or _CHECK_ID.fullmatch(self.check_id) is None:
            raise ValueError("invalid verification check id")
        if self.kind not in ("build", "lint", "test") or type(self.kind) is not str:
            raise ValueError("invalid verification kind")
        if type(self.required) is not bool:
            raise ValueError("required must be boolean")
        if (type(self.argv) is not tuple or not 1 <= len(self.argv) <= 256
                or any(not _text(part) for part in self.argv)
                or sum(len(part.encode("utf-8")) for part in self.argv) > MAX_ARGV_BYTES):
            raise ValueError("verification argv must be a bounded tuple")
        if not _text(self.cwd) or not self.cwd:
            raise ValueError("invalid verification cwd")
        cwd = PurePosixPath(self.cwd)
        if cwd.is_absolute() or ".." in cwd.parts or "\\" in self.cwd or ":" in self.cwd:
            raise ValueError("verification cwd must be workspace-relative")
        if (type(self.timeout_seconds) not in (int, float)
                or not 0 < self.timeout_seconds <= MAX_PLAN_TIMEOUT_SECONDS
                or not math.isfinite(self.timeout_seconds)):
            raise ValueError("verification timeout must be positive and finite")
        if (type(self.output_limit_bytes) is not int
                or not 1 <= self.output_limit_bytes <= MAX_PLAN_OUTPUT_BYTES):
            raise ValueError("invalid verification output limit")
        adapters = ("unittest_summary_v1", "go_test_json_v1") if self.kind == "test" else ("exit_status_v1",)
        if type(self.adapter) is not str or self.adapter not in adapters:
            raise ValueError("unsupported verification adapter")
        executable = Path(self.argv[0])
        if not executable.is_absolute():
            raise ValueError("verification executable must be absolute")
        try:
            identity = _executable_identity(executable)
        except (OSError, RuntimeError, ValueError):
            raise ValueError("verification executable is unavailable") from None
        object.__setattr__(self, "executable_identity", identity)
        if self.adapter == "unittest_summary_v1" and self.argv[1:4] != ("-B", "-m", "unittest"):
            raise ValueError("unittest adapter requires the actual unittest module")
        if self.adapter == "go_test_json_v1":
            packages = self.argv[1 + len(_GO_PREFIX):]
            if (executable.name.lower().removesuffix(".exe") != "go"
                    or self.argv[1:1 + len(_GO_PREFIX)] != _GO_PREFIX or not packages
                    or any(not re.fullmatch(r"\./[A-Za-z0-9_./-]+", item) or ".." in PurePosixPath(item.replace("...", "ALL")).parts
                           for item in packages)):
                raise ValueError("Go adapter requires fixed uncached serial test arguments")
        # Known build frontends must not receive unlimited or >6 parallelism.
        head = executable.name.lower().removesuffix(".exe")
        parallel_declared = False
        if head in ("make", "gmake", "ninja", "cmake", "go"):
            for index, value in enumerate(self.argv[1:], 1):
                if value.startswith("--jobserver-"):
                    raise ValueError("external build jobserver is not part of the frozen plan")
                cluster = re.fullmatch(r"-[bBdehikLmnpqrRsStvw]*j([0-9]*)", value) if head in ("make", "gmake", "cmake") else None
                if value in ("-j", "--jobs", "--parallel", "-p", "-parallel") or cluster and not cluster[1]:
                    value = self.argv[index + 1] if index + 1 < len(self.argv) else ""
                elif cluster:
                    value = cluster[1]
                elif value.startswith(("-p=", "-parallel=")) or (
                        head != "go" and value.startswith(("-j", "--jobs=", "--parallel="))):
                    value = value.split("=", 1)[-1] if "=" in value else value[2:]
                else:
                    continue
                parallel_declared = True
                if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 6:
                    raise ValueError("build parallelism must be between one and six")
        if ((head == "ninja" or head == "cmake" and "--build" in self.argv
             or head == "go" and len(self.argv) > 1 and self.argv[1] in ("build", "test", "install", "run", "vet"))
                and not parallel_declared):
            raise ValueError("this build frontend requires explicit bounded parallelism")

    def _record(self) -> dict:
        return {name: getattr(self, name) for name in (
            "check_id", "kind", "argv", "adapter", "cwd", "required",
            "timeout_seconds", "output_limit_bytes", "executable_identity",
        )}


@dataclass(frozen=True)
class VerificationPlan:
    workspace_root: Path
    run_id: str
    ticket_id: str
    checks: tuple[VerificationCheck, ...]
    steps: tuple[str, ...] = ("task", "code", "deepcheck")
    platforms: tuple[str, ...] = ("Linux", "Darwin", "Windows")
    workspace_identity: tuple[int, int] = field(init=False)
    environment: tuple[tuple[str, str], ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path) or not self.workspace_root.is_absolute():
            raise ValueError("verification workspace must be an absolute Path")
        try:
            root = self.workspace_root.resolve(strict=True)
            status = root.lstat()
            if not stat.S_ISDIR(status.st_mode):
                raise ValueError("invalid verification workspace")
        except (OSError, RuntimeError, ValueError):
            raise ValueError("verification workspace is unavailable") from None
        if any(not _text(item, max_bytes=256) or not item for item in (self.run_id, self.ticket_id)):
            raise ValueError("verification run/ticket identity is required")
        if (type(self.checks) is not tuple or not 1 <= len(self.checks) <= MAX_CHECKS
                or any(type(item) is not VerificationCheck for item in self.checks)
                or len({item.check_id for item in self.checks}) != len(self.checks)
                or not any(item.required and item.kind == "test" for item in self.checks)
                or sum(item.output_limit_bytes for item in self.checks) > MAX_PLAN_OUTPUT_BYTES
                or sum(item.timeout_seconds for item in self.checks) > MAX_PLAN_TIMEOUT_SECONDS):
            raise ValueError("invalid or insufficient verification plan")
        if (type(self.steps) is not tuple or not self.steps
                or any(type(item) is not str for item in self.steps)
                or len(set(self.steps)) != len(self.steps)
                or any(item not in ("task", "code", "deepcheck") for item in self.steps)):
            raise ValueError("unsupported verification steps")
        if (type(self.platforms) is not tuple or not self.platforms
                or any(type(item) is not str for item in self.platforms)
                or len(set(self.platforms)) != len(self.platforms)
                or any(item not in ("Linux", "Darwin", "Windows") for item in self.platforms)):
            raise ValueError("unsupported verification platforms")
        object.__setattr__(self, "workspace_root", root)
        object.__setattr__(self, "workspace_identity", (status.st_dev, status.st_ino))
        object.__setattr__(self, "environment", tuple(sorted(_policy_environment(root).items())))

    @property
    def digest(self) -> str:
        return _canonical_digest({"schema_version": 1, "workspace_root": str(self.workspace_root),
                                  "workspace_identity": self.workspace_identity,
                                  "run_id": self.run_id, "ticket_id": self.ticket_id,
                                  "steps": self.steps, "platforms": self.platforms,
                                  "environment": self.environment,
                                  "checks": [item._record() for item in self.checks]})


@dataclass(frozen=True)
class EngineeringCheckResult:
    check_id: str
    status: str
    exit_code: int | None = None
    tests_passed: int = 0
    output: bytes | None = None
    cleanup_ok: bool | None = None
    cleanup_scope: str = "unknown"
    cache_owner_cleanup_confirmed: bool | None = None
    scope_cleanup_ok: bool | None = None
    resource_channel_status: str = "not_required"
    violation_observer_status: str = "not_required"
    resource_receipt_sha256: str = ""
    error: str = ""

    @property
    def output_sha256(self) -> str:
        return hashlib.sha256(self.output).hexdigest() if self.output is not None else ""


@dataclass(frozen=True)
class EngineeringVerificationRun:
    plan_digest: str
    step: str
    attempt: str
    status: str
    checks: tuple[EngineeringCheckResult, ...]
    source_before: str = ""
    source_after: str = ""
    os_enforced: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "passed" and bool(self.checks) and all(item.status == "passed" for item in self.checks)


def _unittest_count(output: str) -> int:
    matches = list(_SUMMARY.finditer(output))
    if len(matches) != 1 or len(re.findall(r"(?m)^Ran [0-9]+ tests? in\b", output)) != 1:
        return 0
    count = int(matches[0].group(1))
    ending = matches[0].group(2)
    if ending != "OK":
        options = ending[4:-1].split(", ")
        seen = set()
        for option in options:
            match = re.fullmatch(r"(skipped|expected failures)=([0-9]{1,7})", option)
            if match is None or match[1] in seen:
                return 0
            seen.add(match[1])
            count -= int(match[2])
    return max(0, count)


def _go_count(output: str) -> int:
    if not output or not output.endswith("\n"):
        return 0
    packages: dict[str, str] = {}
    tests: dict[tuple[str, str], str] = {}
    open_tests: dict[str, int] = {}
    started_tests: dict[str, int] = {}
    count = 0
    for number, line in enumerate(io.StringIO(output), 1):
        if number > MAX_JSON_EVENTS or len(line.encode("utf-8")) > MAX_ARGV_BYTES:
            return 0
        try:
            event = loads_json_value(line)
        except (TypeError, ValueError, RecursionError):
            return 0
        if type(event) is not dict or type(event.get("Action")) is not str:
            return 0
        action = event["Action"]
        if action in ("build-output", "build-fail"):
            if (set(event) - {"Action", "ImportPath", "Output"}
                    or any(not _text(value) if key != "Output" else not (
                        type(value) is str and len(value.encode("utf-8")) <= MAX_ARGV_BYTES)
                        for key, value in event.items())
                    or action == "build-fail"):
                return 0
            continue
        if set(event) - _GO_FIELDS:
            return 0
        for key, value in event.items():
            if key == "Elapsed":
                if (type(value) not in (int, float) or not 0 <= value <= 1e12
                        or not math.isfinite(value)):
                    return 0
            elif key in ("Output", "Value"):
                if type(value) is not str or len(value.encode("utf-8")) > MAX_ARGV_BYTES:
                    return 0
            elif not _text(value):
                return 0
        package = event.get("Package", "")
        test = event.get("Test", "")
        if not package:
            return 0
        if action == "start":
            if test or package in packages:
                return 0
            packages[package] = "started"
            open_tests[package] = started_tests[package] = 0
            continue
        if packages.get(package) != "started":
            return 0
        if action in ("output", "attr", "artifacts"):
            # Converter output may follow a terminal test report. These events
            # add no execution credit and paths are never read by the host.
            if action == "output" and "Output" not in event:
                return 0
            if action == "attr" and "Key" not in event:
                return 0
            if action == "artifacts" and not event.get("Path"):
                return 0
            continue
        if test:
            if not test.split("/", 1)[0].startswith(("Test", "Example", "Fuzz")):
                return 0
            identity = (package, test)
            previous = tests.get(identity)
            if action == "run" and previous in (None, "pass", "skip"):
                tests[identity] = "running"
                open_tests[package] += 1
                started_tests[package] += 1
            elif action == "pause" and previous == "running":
                tests[identity] = "paused"
            elif action == "cont" and previous == "paused":
                tests[identity] = "running"
            elif action in ("pass", "skip") and previous == "running":
                tests[identity] = action
                open_tests[package] -= 1
                count += action == "pass" and test.startswith("Test")
            elif action == "pass" and previous == "pass":
                # test2json can flush a pending ---PASS at ===PASS and emit
                # the same terminal again. That is not a second invocation.
                continue
            else:
                return 0
        elif action in ("pass", "skip"):
            if open_tests[package]:
                return 0
            if action == "skip" and started_tests[package]:
                return 0
            packages[package] = action
        else:
            return 0
    if not packages or any(state not in ("pass", "skip") for state in packages.values()):
        return 0
    return count


def parse_test_result(adapter: str, output: bytes) -> int:
    """Count reported passes in one complete bounded stream, not test quality."""
    if type(output) is not bytes or len(output) > MAX_PLAN_OUTPUT_BYTES:
        return 0
    try:
        text = output.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return 0
    if adapter == "unittest_summary_v1":
        return _unittest_count(text)
    if adapter == "go_test_json_v1":
        return _go_count(text)
    return 0


def _context_matches(plan: VerificationPlan, ctx: ToolContext, step: str) -> bool:
    if (ctx.read_only_workspace or ctx.sandbox is None or step not in plan.steps
            or platform.system() not in plan.platforms):
        return False
    try:
        root = plan.workspace_root
        status = root.lstat()
        if (ctx.root.resolve(strict=True) != root or not stat.S_ISDIR(status.st_mode)
                or (status.st_dev, status.st_ino) != plan.workspace_identity
                or tuple(sorted(_policy_environment(root).items())) != plan.environment):
            return False
    except (OSError, RuntimeError, ValueError):
        return False
    policy = ctx.policy
    return policy is None or (policy.workspace_root == root and policy.run_id == plan.run_id
                              and policy.ticket_id == plan.ticket_id and policy.step == step)


def _resource_receipt_valid(resource: object) -> bool:
    """Validate the closed host producer shape before hashing any values."""
    if type(resource) is not dict or len(resource) != 7 or set(resource) != {
            "schema_version", "resource", "limit", "configured", "payload_started", "terminal", "channel_status"}:
        return False
    return (type(resource["schema_version"]) is int and resource["schema_version"] == 1
            and type(resource["resource"]) is str and resource["resource"] == "linux_payload_tasks"
            and type(resource["limit"]) is int and 0 < resource["limit"] <= 2 ** 31 - 1
            and type(resource["configured"]) is bool
            and (resource["payload_started"] is None or type(resource["payload_started"]) is bool)
            and (resource["terminal"] is None or type(resource["terminal"]) is str
                 and resource["terminal"] in ("preexec_failed", "finished", "cleanup_failed"))
            and type(resource["channel_status"]) is str
            and resource["channel_status"] in ("complete", "incomplete"))


def _execute_check(check: VerificationCheck, ctx: ToolContext, cache: Path | None) -> EngineeringCheckResult:
    try:
        if _executable_identity(Path(check.argv[0])) != check.executable_identity:
            return EngineeringCheckResult(check.check_id, "tool_changed", cleanup_scope="not_started",
                                          cache_owner_cleanup_confirmed=True)
    except (OSError, ValueError):
        return EngineeringCheckResult(check.check_id, "missing_command", cleanup_scope="not_started",
                                      cache_owner_cleanup_confirmed=True)
    try:
        cwd = (ctx.root / check.cwd).resolve(strict=True)
        cwd.relative_to(ctx.root.resolve(strict=True))
        if not cwd.is_dir():
            raise ValueError("invalid check cwd")
    except (OSError, RuntimeError, ValueError):
        return EngineeringCheckResult(check.check_id, "execution_unavailable", error="invalid_cwd",
                                      cleanup_scope="not_started", cache_owner_cleanup_confirmed=True)
    from . import runner
    try:
        if ctx.policy is not None:
            from .tools.builtin import _controlled_dispatch
            outcome = _controlled_dispatch(
                ctx, list(check.argv), cwd=cwd, timeout=check.timeout_seconds,
                output_limit_bytes=check.output_limit_bytes, require_resource=True,
                verification_cache_root=cache,
            )
            resource = outcome.resource_receipt
            resource_valid = _resource_receipt_valid(resource)
            complete = (
                outcome.error is None and outcome.cleanup_ok is True
                and outcome.scope_cleanup_ok is True and not outcome.output_truncated
                and outcome.violation_receipt is None and outcome.violation_observer_status == "complete"
                and type(outcome.exit_code) is int
                and resource_valid and resource["limit"] == ctx.policy.process_limit
                and resource.get("configured") is True and resource.get("terminal") == "finished"
                and resource.get("payload_started") is None
                and resource.get("channel_status") == "complete"
                and type(outcome.raw_output) is bytes and type(outcome.output_bytes) is int
                and len(outcome.raw_output) == outcome.output_bytes <= check.output_limit_bytes
            )
            facts = dict(cleanup_ok=outcome.cleanup_ok, scope_cleanup_ok=outcome.scope_cleanup_ok,
                         cleanup_scope="linux_task_scope",
                         cache_owner_cleanup_confirmed=(resource_valid and outcome.cleanup_ok is True
                                                        and outcome.scope_cleanup_ok is True),
                         resource_channel_status=resource["channel_status"] if resource_valid else "incomplete",
                         violation_observer_status="complete" if outcome.violation_observer_status == "complete" else "incomplete",
                         resource_receipt_sha256=_canonical_digest(resource) if resource_valid else "")
            if not complete:
                return EngineeringCheckResult(check.check_id, "output_incomplete",
                    exit_code=outcome.exit_code if type(outcome.exit_code) is int else None,
                    error="execution_receipt_incomplete", **facts)
            code, output = outcome.exit_code, outcome.raw_output
        else:
            environment = _policy_environment(ctx.root.resolve(), verification_cache_root=cache)
            prepared = ctx.wrap_command(list(check.argv), network=False)
            if getattr(prepared, "pass_fds", ()) or getattr(prepared, "cwd", cwd) != cwd:
                raise IsolationUnavailable("该非策略检查不能保留包装器启动合同")
            code, stdout, stderr = runner._run_unittest_with_bounded_output(
                list(prepared), workspace=cwd, timeout=check.timeout_seconds,
                output_limit_bytes=check.output_limit_bytes, environment=environment,
            )
            output = stdout + stderr
            # The old POSIX reader confirms only its process group, not
            # detached cache writers. Do not upgrade its tuple into tree proof.
            facts = dict(cleanup_ok=True, cleanup_scope="job_tree" if os.name == "nt" else "process_group",
                         cache_owner_cleanup_confirmed=True if os.name == "nt" else None)
    except IsolationUnavailable:
        return EngineeringCheckResult(check.check_id, "execution_unavailable", error="isolation_unavailable")
    except (runner.VerificationOutputError, subprocess.TimeoutExpired, OSError) as error:
        # No partial stream, exception text/argv, or guessed cleanup credit.
        return EngineeringCheckResult(check.check_id, "output_incomplete", error=type(error).__name__)
    try:
        if _executable_identity(Path(check.argv[0])) != check.executable_identity:
            return EngineeringCheckResult(check.check_id, "tool_changed", exit_code=code, **facts)
    except (OSError, ValueError):
        return EngineeringCheckResult(check.check_id, "tool_changed", exit_code=code, **facts)
    count = parse_test_result(check.adapter, output) if type(code) is int and code == 0 else 0
    passed = type(code) is int and code == 0 and (check.kind != "test" or count > 0)
    return EngineeringCheckResult(check.check_id, "passed" if passed else "failed", exit_code=code,
                                  tests_passed=count, output=output, **facts)


@contextlib.contextmanager
def _local_descriptor(descriptor: int):
    """Close a local FD while preserving cleanup exception priority."""
    try:
        yield descriptor
    except BaseException as error:
        try:
            os.close(descriptor)
        except BaseException as cleanup_error:
            selected = _select_cleanup_error(error, cleanup_error)
            if selected is not error:
                raise selected
        raise
    else:
        os.close(descriptor)


class _PinnedVerificationCache:
    """Own one fresh POSIX directory object, not a reusable pathname/inode pair.

    Handles are never inherited by payloads. Holding the original object also
    prevents delete/recreate inode ABA from being accepted as host ownership.
    Windows cache execution remains unavailable until its held-HANDLE deletion
    lifecycle is independently implemented and validated.
    """

    def __init__(self, plan: VerificationPlan):
        if os.name != "posix":
            raise ValueError("held verification cache is unavailable on this platform")
        self.parent = plan.workspace_root
        self.parent_fd = None
        self.descriptor = None
        self.name = ""
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            self.parent_fd = os.open(self.parent, flags)
            parent_status = os.fstat(self.parent_fd)
            if (parent_status.st_dev, parent_status.st_ino) != plan.workspace_identity:
                raise ValueError("verification workspace object changed")
            for _ in range(10):
                candidate = ".icode-verification-" + secrets.token_hex(16)
                try:
                    os.mkdir(candidate, mode=0o700, dir_fd=self.parent_fd)
                except FileExistsError:
                    continue
                self.name = candidate
                break
            if not self.name:
                raise ValueError("unable to create a fresh verification cache")
            self.path = self.parent / self.name
            self.descriptor = os.open(self.name, flags, dir_fd=self.parent_fd)
            for name in ("tmp", "cache", "mod", "gopath", "home", "config", "local"):
                os.mkdir(name, mode=0o700, dir_fd=self.descriptor)
            # GOTELEMETRY is a reported setting, not an env override. Only new
            # owned config is changed, never the user's mode or counters.
            for parts in (("config", "go", "telemetry"),
                          ("home", "Library", "Application Support", "go", "telemetry")):
                with contextlib.ExitStack() as descriptors:
                    directory = descriptors.enter_context(_local_descriptor(os.dup(self.descriptor)))
                    for part in parts:
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=directory)
                        except FileExistsError:
                            pass
                        directory = descriptors.enter_context(_local_descriptor(
                            os.open(part, flags, dir_fd=directory)))
                    with _local_descriptor(os.open(
                            "mode", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=directory)) as mode:
                        if os.write(mode, b"off\n") != 4:
                            raise OSError("incomplete owned telemetry configuration")
            if not self.matches():
                raise ValueError("verification cache object changed")
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                selected = _select_cleanup_error(error, cleanup_error)
                if selected is not error:
                    raise selected
            raise

    def matches(self) -> bool:
        try:
            parent = os.fstat(self.parent_fd)
            current_parent = self.parent.lstat()
            held = os.fstat(self.descriptor)
            current = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            return (
                parent.st_nlink > 0 and held.st_nlink > 0
                and stat.S_ISDIR(current_parent.st_mode) and stat.S_ISDIR(current.st_mode)
                and (parent.st_dev, parent.st_ino) == (current_parent.st_dev, current_parent.st_ino)
                and (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino)
                and self.path.resolve(strict=True) == self.path
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    def remove(self) -> None:
        if not self.matches() or not shutil.rmtree.avoids_symlink_attacks:
            raise ValueError("owned verification cache cleanup is unavailable")
        # The recursive traversal must consume our already held object. A
        # fresh rmtree(name, parent_fd) could instead open a real replacement
        # after matches(); its symlink protection would not detect that swap.
        # Writers must already be collected; other host processes are trusted.
        with os.scandir(self.descriptor) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.name, dir_fd=self.descriptor)
                else:
                    os.unlink(entry.name, dir_fd=self.descriptor)
        if not self.matches():
            raise ValueError("owned verification cache changed during cleanup")
        os.rmdir(self.name, dir_fd=self.parent_fd)

    def close(self) -> None:
        error = None
        for name in ("descriptor", "parent_fd"):
            descriptor = getattr(self, name, None)
            setattr(self, name, None)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException as caught:
                    error = _select_cleanup_error(error, caught)
        if error is not None:
            raise error


def execute_verification_plan(
    plan: VerificationPlan, *, ctx: ToolContext, step: str, attempt: str,
) -> EngineeringVerificationRun:
    """Actually execute a frozen host plan; old runner/receipt APIs are separate."""
    if type(plan) is not VerificationPlan or not isinstance(ctx, ToolContext):
        raise ValueError("host verification requires a frozen plan and context")
    if not _text(attempt, max_bytes=256) or not attempt or not _text(step, max_bytes=64):
        raise ValueError("verification step/attempt identity is required")
    digest = plan.digest
    results = tuple(EngineeringCheckResult(item.check_id, "not_run") for item in plan.checks)
    if not _context_matches(plan, ctx, step):
        return EngineeringVerificationRun(digest, step, attempt, "execution_unavailable", results)
    # A policy check has no ordinary subprocess fallback on unsupported hosts.
    if ctx.policy is not None:
        from .tools.builtin import _uses_resource_dispatch
        if not _uses_resource_dispatch(ctx):
            return EngineeringVerificationRun(digest, step, attempt, "execution_unavailable", results)
        try:
            ctx._policy_command_wrapper()
        except IsolationUnavailable:
            return EngineeringVerificationRun(digest, step, attempt, "execution_unavailable", results)
    try:
        before_snapshot = snapshot_workspace(plan.workspace_root)
    except (OSError, WorktreeTreeUnavailable):
        return EngineeringVerificationRun(digest, step, attempt, "source_unavailable", results)
    before = snapshot_fingerprint(before_snapshot)
    cache = None
    owned_cache = None
    if any(Path(item.argv[0]).name.lower().removesuffix(".exe") == "go" for item in plan.checks):
        try:
            owned_cache = _PinnedVerificationCache(plan)
            cache = owned_cache.path
        except (OSError, RuntimeError, ValueError):
            return EngineeringVerificationRun(digest, step, attempt, "execution_unavailable", results,
                                              source_before=before)
    outcomes = []
    status = "passed"
    cleanup_confirmed = True
    try:
        for check in plan.checks:
            if status != "passed":
                outcomes.append(EngineeringCheckResult(check.check_id, "not_run"))
                continue
            if owned_cache is not None and not owned_cache.matches():
                status = "cache_cleanup_unconfirmed"
                outcomes.append(EngineeringCheckResult(check.check_id, "not_run"))
                continue
            if plan.digest != digest or not _context_matches(plan, ctx, step):
                result = EngineeringCheckResult(check.check_id, "execution_unavailable", error="binding_changed")
            else:
                result = _execute_check(check, ctx, cache)
            outcomes.append(result)
            if cache is not None and result.cache_owner_cleanup_confirmed is not True:
                cleanup_confirmed = False
                status = "cache_cleanup_unconfirmed"
                continue
            if result.status != "passed":
                status = result.status
            elif status == "passed":
                if owned_cache is not None and not owned_cache.matches():
                    status = "cache_cleanup_unconfirmed"
                    continue
                if not _context_matches(plan, ctx, step):
                    status = "binding_changed"
                    continue
                try:
                    observed = snapshot_workspace(plan.workspace_root)
                except (OSError, WorktreeTreeUnavailable):
                    status = "source_unavailable"
                    continue
                if cache is not None:
                    # Intermediate early-stop check only: omit exactly the
                    # host-owned ephemeral object, never a general build or
                    # gitignored directory. Final full snapshot is taken only
                    # after confirmed owned-cache cleanup.
                    prefix = cache.name + "/"
                    observed = {name: digest for name, digest in observed.items()
                                if not name.startswith(prefix)}
                if observed != before_snapshot:
                    status = "source_changed"
            if result.cleanup_ok is not True and result.status not in ("tool_changed", "missing_command", "execution_unavailable"):
                cleanup_confirmed = False
            if ctx.policy is not None and result.scope_cleanup_ok is not True and result.status == "output_incomplete":
                cleanup_confirmed = False
    except BaseException as error:
        # Owned cache is retained when exceptional cleanup cannot be observed.
        # Do not replace a KeyboardInterrupt/SystemExit with a deletion failure.
        if owned_cache is not None:
            try:
                owned_cache.close()
            except BaseException as cleanup_error:
                selected = _select_cleanup_error(error, cleanup_error)
                if selected is not error:
                    raise selected
        raise
    if owned_cache is not None:
        cleanup_error = None
        try:
            if not cleanup_confirmed:
                raise ValueError("owned cache writers are not confirmed collected")
            owned_cache.remove()
        except (OSError, RuntimeError, ValueError):
            status = "cache_cleanup_unconfirmed"
        except BaseException as error:
            cleanup_error = error
        finally:
            try:
                owned_cache.close()
            except BaseException as error:
                cleanup_error = _select_cleanup_error(cleanup_error, error)
            if isinstance(cleanup_error, OSError):
                status = "cache_cleanup_unconfirmed"
            elif cleanup_error is not None:
                raise cleanup_error
    # Do not observe a replacement workspace after the original binding was
    # lost. No source-after fingerprint is invented for that unknown object.
    if not _context_matches(plan, ctx, step):
        return EngineeringVerificationRun(digest, step, attempt, "binding_changed", tuple(outcomes), before)
    try:
        after = snapshot_fingerprint(snapshot_workspace(plan.workspace_root))
    except (OSError, WorktreeTreeUnavailable):
        return EngineeringVerificationRun(digest, step, attempt, "source_unavailable", tuple(outcomes), before)
    if status == "passed" and (plan.digest != digest or not _context_matches(plan, ctx, step)):
        status = "binding_changed"
    if status == "passed" and before != after:
        status = "source_changed"
    return EngineeringVerificationRun(digest, step, attempt, status, tuple(outcomes), before, after,
                                      os_enforced=ctx.policy is not None and status == "passed")
