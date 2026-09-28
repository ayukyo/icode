"""Test-only diagnostics for macOS Seatbelt violation logging.

This module never feeds product receipts. It retains only PID/capability pairs
from a bounded Unified Logging stream and treats missing observations as
inconclusive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable


SUBSYSTEM = "com.apple.sandbox.reporting"
CATEGORY = "violation"
PREDICATE = (
    '(processID == 0 AND senderImagePath CONTAINS "/Sandbox") OR '
    f'(subsystem == "{SUBSYSTEM}" AND category == "{CATEGORY}") OR '
    'eventMessage CONTAINS[c] "Sandbox"'
)
MAX_RECORD_BYTES = 16 * 1024
MAX_STREAM_BYTES = 1024 * 1024
MAX_RECORDS = 4096
LOGGER_START_GRACE_SECONDS = 0.5
LOGGER_STOP_TIMEOUT_SECONDS = 2.0
READER_JOIN_TIMEOUT_SECONDS = 2.0
TARGET_EVENT_WAIT_SECONDS = 5.0

_LOG_STREAM_FILTER_BANNER_PREFIX = b"Filtering the log data using "
_DIAGNOSTIC_COUNTERS = (
    "stdout_lines", "stderr_lines", "stdout_json", "stderr_json",
    "stdout_non_json", "stderr_non_json", "filter_banner",
    "json_object", "json_non_object", "subsystem_match", "category_match",
    "source_reporting", "source_kernel", "source_other",
    "message_type_default", "message_type_info",
    "message_type_debug", "message_type_error", "message_type_fault",
    "message_type_other", "emitter_pid_zero", "emitter_pid_nonzero",
    "emitter_pid_other", "sender_path_sandbox", "sender_path_other",
    "sender_path_missing", "deny_message", "deny_unparsed", "message_other",
    "message_missing", "capability_file_read_data", "capability_other",
)
_MESSAGE_TYPES = {"default", "info", "debug", "error", "fault"}
_DENIAL_MESSAGE = re.compile(
    r"^Sandbox:\s+[^()\r\n]{1,128}\((?P<pid>[0-9]{1,10})\)\s+"
    r"deny\([0-9]+\)\s+(?P<capability>[a-z][a-z0-9-]{0,63})(?:\s|$)"
)


class ViolationRecordError(ValueError):
    """A matching system log record could not be parsed safely."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ViolationObserverUnavailable(RuntimeError):
    """The native log stream could not be started or remained unavailable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Observation:
    status: str
    reason: str
    diagnostics: str = ""


def parse_violation_record(line: bytes) -> tuple[int, str] | None:
    """Parse one NDJSON line, returning only the denied PID and capability."""

    if len(line) > MAX_RECORD_BYTES:
        raise ViolationRecordError("record_too_large")
    try:
        record = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ViolationRecordError("invalid_json") from None
    if not isinstance(record, dict):
        raise ViolationRecordError("invalid_record_shape")
    subsystem_match = record.get("subsystem") == SUBSYSTEM
    category_match = record.get("category") == CATEGORY
    reporting_source = subsystem_match and category_match
    process_id = record.get("processID")
    sender_image = record.get("senderImagePath")
    kernel_source = (
        type(process_id) is int
        and process_id == 0
        and isinstance(sender_image, str)
        and "/Sandbox" in sender_image
    )
    if not (reporting_source or kernel_source):
        return None

    message = record.get("eventMessage")
    if not isinstance(message, str):
        raise ViolationRecordError("missing_event_message")
    match = _DENIAL_MESSAGE.match(message)
    if match is None:
        raise ViolationRecordError("unparsed_event_message")

    pid = int(match.group("pid"))
    if pid <= 0:
        raise ViolationRecordError("invalid_pid")
    return pid, match.group("capability")


def diagnostic_record_categories(line: bytes) -> tuple[str, ...]:
    """Return fixed, content-free buckets for one log record."""

    try:
        record = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ("invalid_json",)
    if not isinstance(record, dict):
        return ("json_non_object",)

    categories = ["json_object"]
    message_type = record.get("messageType")
    if isinstance(message_type, str) and message_type in _MESSAGE_TYPES:
        categories.append(f"message_type_{message_type}")
    else:
        categories.append("message_type_other")

    process_id = record.get("processID")
    if type(process_id) is not int:
        categories.append("emitter_pid_other")
    elif process_id == 0:
        categories.append("emitter_pid_zero")
    else:
        categories.append("emitter_pid_nonzero")

    sender_image = record.get("senderImagePath")
    if not isinstance(sender_image, str):
        categories.append("sender_path_missing")
    elif "/Sandbox" in sender_image:
        categories.append("sender_path_sandbox")
    else:
        categories.append("sender_path_other")

    subsystem_match = record.get("subsystem") == SUBSYSTEM
    category_match = record.get("category") == CATEGORY
    reporting_source = subsystem_match and category_match
    kernel_source = (
        type(process_id) is int
        and process_id == 0
        and isinstance(sender_image, str)
        and "/Sandbox" in sender_image
    )
    if subsystem_match:
        categories.append("subsystem_match")
    if category_match:
        categories.append("category_match")
    if reporting_source:
        categories.append("source_reporting")
    if kernel_source:
        categories.append("source_kernel")
    if not reporting_source and not kernel_source:
        categories.append("source_other")

    message = record.get("eventMessage")
    if not isinstance(message, str):
        categories.append("message_missing")
    else:
        match = _DENIAL_MESSAGE.match(message)
        if match is None:
            if message.startswith("Sandbox:"):
                categories.append("deny_unparsed")
            else:
                categories.append("message_other")
        else:
            categories.append("deny_message")
            if match.group("capability") == "file-read-data":
                categories.append("capability_file_read_data")
            else:
                categories.append("capability_other")
    return tuple(categories)


def format_sanitized_diagnostics(
    counts: Mapping[str, int],
    *,
    events: Iterable[tuple[int, str]],
    target_pid: int,
    capability: str,
    logger_returncode: int | None,
) -> str:
    """Render only bounded counts and booleans; never include log values."""

    count = lambda name: max(0, int(counts.get(name, 0)))
    target_match = any(
        pid == target_pid and item == capability for pid, item in events
    )
    if logger_returncode is None:
        logger_state = "running"
    elif logger_returncode == 0:
        logger_state = "exit_zero"
    else:
        logger_state = "exit_nonzero"

    return (
        f"lines=out:{count('stdout_lines')},err:{count('stderr_lines')} "
        f"json=out:{count('stdout_json')},err:{count('stderr_json')},"
        f"bad:{count('stdout_non_json') + count('stderr_non_json')} "
        f"sources=subsystem:{count('subsystem_match')},"
        f"category:{count('category_match')},reporting:{count('source_reporting')},"
        f"kernel:{count('source_kernel')},other:{count('source_other')} "
        f"types=default:{count('message_type_default')},"
        f"info:{count('message_type_info')},debug:{count('message_type_debug')},"
        f"error:{count('message_type_error')},fault:{count('message_type_fault')},"
        f"other:{count('message_type_other')} "
        f"sender=pid0:{count('emitter_pid_zero')},"
        f"pidn:{count('emitter_pid_nonzero')},pid?:{count('emitter_pid_other')},"
        f"path_sandbox:{count('sender_path_sandbox')},"
        f"path_other:{count('sender_path_other')},"
        f"path?:{count('sender_path_missing')} "
        f"deny:parsed={count('deny_message')},unparsed={count('deny_unparsed')},"
        f"file_read_data={count('capability_file_read_data')},"
        f"other_cap={count('capability_other')},"
        f"message_other={count('message_other')},"
        f"message_missing={count('message_missing')} "
        f"target_match={'yes' if target_match else 'no'} "
        f"log_process={logger_state} banners={count('filter_banner')}"
    )


def build_log_stream_command(executable: Path) -> list[str]:
    """Build a bounded observer command that includes debug-level log records."""

    return [
        str(executable), "stream", "--style", "ndjson",
        "--level", "debug", "--predicate", PREDICATE,
    ]


def parse_violation_stream_line(
    line: bytes,
    *,
    first_line: bool,
) -> tuple[int, str] | None:
    """Parse one bounded stream line, allowing only the known initial CLI banner."""

    if len(line) > MAX_RECORD_BYTES:
        raise ViolationRecordError("record_too_large")
    if not line.endswith(b"\n"):
        raise ViolationRecordError("record_size_or_truncation")
    if first_line and line.startswith(_LOG_STREAM_FILTER_BANNER_PREFIX):
        # The CLI may write a human-readable filter banner before NDJSON. Drop
        # it immediately; never retain or expose its predicate text.
        return None
    return parse_violation_record(line)


def classify_observation(
    events: Iterable[tuple[int, str]],
    *,
    target_pid: int,
    capability: str,
    incomplete_reason: str | None = None,
) -> Observation:
    """A positive exact match is evidence; every absence remains inconclusive."""

    if any(pid == target_pid and item == capability for pid, item in events):
        return Observation(status="observed", reason="matching_event")
    if incomplete_reason is not None:
        return Observation("inconclusive", incomplete_reason)
    return Observation("inconclusive", "target_event_not_observed")


class BoundedViolationLogObserver:
    """Bounded test-only reader for the macOS Unified Logging CLI."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdout is None or process.stderr is None:
            raise ValueError("log stream stdout and stderr are required")
        self._process = process
        self._streams = (
            ("stdout", process.stdout),
            ("stderr", process.stderr),
        )
        self._events: set[tuple[int, str]] = set()
        self._lock = threading.Lock()
        self._changed = threading.Event()
        self._diagnostic_counts = {name: 0 for name in _DIAGNOSTIC_COUNTERS}
        self._total_bytes = 0
        self._total_records = 0
        self._incomplete_reason: str | None = None
        self._closing = False
        self._readers = [
            threading.Thread(
                target=self._read_records,
                args=(name, stream),
                name=f"macos-violation-log-{name}-reader",
                daemon=True,
            )
            for name, stream in self._streams
        ]
        for reader in self._readers:
            reader.start()

    @classmethod
    def start(cls) -> BoundedViolationLogObserver:
        executable = Path("/usr/bin/log")
        if not executable.is_file():
            raise ViolationObserverUnavailable("log_cli_unavailable")
        try:
            process = subprocess.Popen(
                build_log_stream_command(executable),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError:
            raise ViolationObserverUnavailable("log_stream_start_failed") from None

        observer = cls(process)
        time.sleep(LOGGER_START_GRACE_SECONDS)
        if process.poll() is not None:
            observer.close()
            raise ViolationObserverUnavailable("log_stream_exited_early")
        return observer

    def _set_incomplete(self, reason: str) -> None:
        with self._lock:
            if self._incomplete_reason is None:
                self._incomplete_reason = reason
        self._changed.set()

    def _read_records(self, stream_name: str, stream) -> None:
        first_line = True
        try:
            while True:
                line = stream.readline(MAX_RECORD_BYTES + 1)
                if not line:
                    if not self._closing and self._process.poll() is not None:
                        self._set_incomplete("log_stream_ended")
                    return

                with self._lock:
                    self._diagnostic_counts[f"{stream_name}_lines"] += 1
                    self._total_bytes += len(line)
                    self._total_records += 1
                    total_bytes = self._total_bytes
                    total_records = self._total_records
                if total_bytes > MAX_STREAM_BYTES:
                    self._set_incomplete("stream_byte_limit")
                    return

                if len(line) > MAX_RECORD_BYTES or not line.endswith(b"\n"):
                    self._set_incomplete("record_size_or_truncation")
                    return

                if total_records > MAX_RECORDS:
                    self._set_incomplete("stream_record_limit")
                    return
                if first_line and line.startswith(_LOG_STREAM_FILTER_BANNER_PREFIX):
                    with self._lock:
                        self._diagnostic_counts["filter_banner"] += 1
                    first_line = False
                    continue
                first_line = False

                categories = diagnostic_record_categories(line)
                with self._lock:
                    if "json_object" in categories or "json_non_object" in categories:
                        self._diagnostic_counts[f"{stream_name}_json"] += 1
                    if "invalid_json" in categories:
                        self._diagnostic_counts[f"{stream_name}_non_json"] += 1
                    for category in categories:
                        if category in self._diagnostic_counts:
                            self._diagnostic_counts[category] += 1
                try:
                    event = parse_violation_stream_line(
                        line,
                        first_line=False,
                    )
                except ViolationRecordError as error:
                    self._set_incomplete(error.reason)
                    continue
                except Exception:
                    self._set_incomplete("record_parse_failed")
                    continue
                if event is not None:
                    with self._lock:
                        self._events.add(event)
                    self._changed.set()
        except Exception:
            if not self._closing:
                self._set_incomplete("log_stream_read_failed")

    def _observation(
        self,
        *,
        events: tuple[tuple[int, str], ...],
        incomplete_reason: str | None,
        target_pid: int,
        capability: str,
    ) -> Observation:
        result = classify_observation(
            events,
            target_pid=target_pid,
            capability=capability,
            incomplete_reason=incomplete_reason,
        )
        with self._lock:
            counts = dict(self._diagnostic_counts)
        diagnostics = format_sanitized_diagnostics(
            counts,
            events=events,
            target_pid=target_pid,
            capability=capability,
            logger_returncode=self._process.poll(),
        )
        return Observation(result.status, result.reason, diagnostics)

    def observe(self, *, target_pid: int, capability: str) -> Observation:
        deadline = time.monotonic() + TARGET_EVENT_WAIT_SECONDS
        while True:
            with self._lock:
                events = tuple(self._events)
                incomplete_reason = self._incomplete_reason
            result = self._observation(
                events=events,
                incomplete_reason=incomplete_reason,
                target_pid=target_pid,
                capability=capability,
            )
            if result.status == "observed":
                return result
            if self._process.poll() is not None or time.monotonic() >= deadline:
                return result
            self._changed.wait(timeout=0.05)
            self._changed.clear()

    def close(self) -> None:
        self._closing = True
        if self._process.poll() is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        try:
            self._process.wait(timeout=LOGGER_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            self._process.wait(timeout=LOGGER_STOP_TIMEOUT_SECONDS)
        for reader in self._readers:
            reader.join(timeout=READER_JOIN_TIMEOUT_SECONDS)
        if any(reader.is_alive() for reader in self._readers):
            self._set_incomplete("log_reader_cleanup_timeout")
        for _, stream in self._streams:
            try:
                stream.close()
            except OSError:
                pass

    def __enter__(self) -> BoundedViolationLogObserver:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
