"""Test-only diagnostics for macOS Seatbelt violation logging.

This module never feeds product receipts. It retains only PID/capability pairs
from a bounded Unified Logging stream and treats missing observations as
inconclusive.
"""

from __future__ import annotations

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
PREDICATE = f'subsystem == "{SUBSYSTEM}" AND category == "{CATEGORY}"'
MAX_RECORD_BYTES = 16 * 1024
MAX_STREAM_BYTES = 1024 * 1024
MAX_RECORDS = 4096
LOGGER_START_GRACE_SECONDS = 0.5
LOGGER_STOP_TIMEOUT_SECONDS = 2.0
READER_JOIN_TIMEOUT_SECONDS = 2.0
TARGET_EVENT_WAIT_SECONDS = 1.0

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
    if record.get("subsystem") != SUBSYSTEM or record.get("category") != CATEGORY:
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
        if process.stdout is None:
            raise ValueError("log stream stdout is required")
        self._process = process
        self._stdout = process.stdout
        self._events: set[tuple[int, str]] = set()
        self._lock = threading.Lock()
        self._changed = threading.Event()
        self._incomplete_reason: str | None = None
        self._closing = False
        self._reader = threading.Thread(
            target=self._read_records,
            name="macos-violation-log-reader",
            daemon=True,
        )
        self._reader.start()

    @classmethod
    def start(cls) -> BoundedViolationLogObserver:
        executable = Path("/usr/bin/log")
        if not executable.is_file():
            raise ViolationObserverUnavailable("log_cli_unavailable")
        try:
            process = subprocess.Popen(
                [
                    str(executable), "stream", "--style", "ndjson",
                    "--predicate", PREDICATE,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
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

    def _read_records(self) -> None:
        total_bytes = 0
        records_seen = 0
        try:
            while True:
                line = self._stdout.readline(MAX_RECORD_BYTES + 1)
                if not line:
                    if not self._closing:
                        self._set_incomplete("log_stream_ended")
                    return

                total_bytes += len(line)
                if total_bytes > MAX_STREAM_BYTES:
                    self._set_incomplete("stream_byte_limit")
                    return

                if len(line) > MAX_RECORD_BYTES or not line.endswith(b"\n"):
                    self._set_incomplete("record_size_or_truncation")
                    return

                records_seen += 1
                if records_seen > MAX_RECORDS:
                    self._set_incomplete("stream_record_limit")
                    return
                try:
                    event = parse_violation_record(line)
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

    def observe(self, *, target_pid: int, capability: str) -> Observation:
        deadline = time.monotonic() + TARGET_EVENT_WAIT_SECONDS
        while True:
            with self._lock:
                events = tuple(self._events)
                incomplete_reason = self._incomplete_reason
            result = classify_observation(
                events,
                target_pid=target_pid,
                capability=capability,
                incomplete_reason=incomplete_reason,
            )
            if result.status == "observed" or incomplete_reason is not None:
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
        self._reader.join(timeout=READER_JOIN_TIMEOUT_SECONDS)
        if self._reader.is_alive():
            self._set_incomplete("log_reader_cleanup_timeout")
        try:
            self._stdout.close()
        except OSError:
            pass

    def __enter__(self) -> BoundedViolationLogObserver:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
