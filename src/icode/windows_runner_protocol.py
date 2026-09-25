"""Versioned, side-effect-free wire validation for the future Windows runner.

This module encodes only a bounded JSON frame. It does not create a pipe,
authenticate a peer, authorize a command, or apply Windows security policy.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import struct
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import NoReturn


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 64 * 1024
MAX_OUTPUT_CHUNK_BYTES = 32 * 1024
MAX_ARGV_ITEMS = 256
MAX_ARGV_BYTES = 48 * 1024
MAX_UINT32 = (1 << 32) - 1

_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
_ERROR_STAGES = frozenset({
    "read_request", "validate_request", "spawn_child", "assign_job",
    "stream_output", "cleanup",
})
_ERROR_CODES = frozenset({
    "invalid_request", "access_denied", "privilege_missing",
    "process_limit", "io_error", "cleanup_failed", "unsupported",
})
_MESSAGE_FIELDS: dict[str, frozenset[str]] = {
    "spawn_request": frozenset({
        "version", "type", "request_id", "argv", "cwd_rel",
        "timeout_ms", "output_limit_bytes",
    }),
    "cancel_request": frozenset({"version", "type", "request_id"}),
    "spawn_ready": frozenset({"version", "type", "request_id"}),
    "output": frozenset({
        "version", "type", "request_id", "sequence", "data_b64",
    }),
    "exit": frozenset({
        "version", "type", "request_id", "exit_code", "timed_out",
        "output_truncated", "cleanup_ok",
    }),
    "error": frozenset({
        "version", "type", "request_id", "stage", "code",
    }),
    "cancel_ack": frozenset({
        "version", "type", "request_id", "cancelled",
    }),
}


class RunnerProtocolError(ValueError):
    """A frame is malformed, unsupported, or outside the v1 contract."""


def _reject(code: str) -> NoReturn:
    raise RunnerProtocolError(code)


def _require_uint32(value: object, field: str, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum or value > MAX_UINT32:
        _reject(f"invalid_{field}")


def _require_string(value: object, field: str, *, allow_empty: bool = True) -> str:
    if type(value) is not str or (not allow_empty and not value):
        _reject(f"invalid_{field}")
    if len(value) > MAX_FRAME_BYTES:
        _reject(f"oversized_{field}")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _reject(f"invalid_{field}")
    if "\x00" in value:
        _reject(f"invalid_{field}")
    return value


def _validate_request_id(value: object) -> str:
    request_id = _require_string(value, "request_id", allow_empty=False)
    if _REQUEST_ID.fullmatch(request_id) is None:
        _reject("invalid_request_id")
    return request_id


def _validate_cwd_rel(value: object) -> None:
    cwd = _require_string(value, "cwd_rel", allow_empty=False)
    if cwd == ".":
        return
    if (
        "\\" in cwd or ":" in cwd or cwd.startswith("/")
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in cwd)
    ):
        _reject("invalid_cwd_rel")
    path = PurePosixPath(cwd)
    if path.as_posix() != cwd or any(part in ("", ".", "..") for part in path.parts):
        _reject("invalid_cwd_rel")


def _validate_spawn_request(message: dict[str, object]) -> None:
    argv = message.get("argv")
    if type(argv) is not list or not 1 <= len(argv) <= MAX_ARGV_ITEMS:
        _reject("invalid_argv")
    total_bytes = 0
    for index, value in enumerate(argv):
        item = _require_string(value, "argv_item")
        if index == 0 and not item.strip():
            _reject("invalid_argv")
        total_bytes += len(item.encode("utf-8"))
    if total_bytes > MAX_ARGV_BYTES:
        _reject("argv_too_large")
    _validate_cwd_rel(message.get("cwd_rel"))
    _require_uint32(message.get("timeout_ms"), "timeout_ms", minimum=1)
    _require_uint32(
        message.get("output_limit_bytes"), "output_limit_bytes", minimum=1,
    )


def _validate_message(message: object) -> dict[str, object]:
    if type(message) is not dict:
        _reject("message_must_be_object")
    if any(type(key) is not str for key in message):
        _reject("invalid_message_field")
    version = message.get("version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        _reject("unsupported_protocol_version")
    message_type = message.get("type")
    if type(message_type) is not str or message_type not in _MESSAGE_FIELDS:
        _reject("unsupported_message_type")
    if set(message) != _MESSAGE_FIELDS[message_type]:
        _reject("invalid_message_fields")
    _validate_request_id(message.get("request_id"))

    if message_type == "spawn_request":
        _validate_spawn_request(message)
    elif message_type == "output":
        _require_uint32(message.get("sequence"), "sequence", minimum=1)
        encoded = _require_string(
            message.get("data_b64"), "output_data", allow_empty=False,
        )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            _reject("invalid_output_data")
        if not raw or len(raw) > MAX_OUTPUT_CHUNK_BYTES:
            _reject("invalid_output_data")
        if base64.b64encode(raw).decode("ascii") != encoded:
            _reject("invalid_output_data")
    elif message_type == "exit":
        _require_uint32(message.get("exit_code"), "exit_code")
        for field in ("timed_out", "output_truncated", "cleanup_ok"):
            if type(message.get(field)) is not bool:
                _reject(f"invalid_{field}")
    elif message_type == "error":
        stage = message.get("stage")
        code = message.get("code")
        if type(stage) is not str or stage not in _ERROR_STAGES:
            _reject("invalid_error_stage")
        if type(code) is not str or code not in _ERROR_CODES:
            _reject("invalid_error_code")
    elif message_type == "cancel_ack":
        if type(message.get("cancelled")) is not bool:
            _reject("invalid_cancelled")
    return message


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _reject("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    _reject("invalid_json_constant")


def encode_frame(message: Mapping[str, object]) -> bytes:
    """Validate and encode one big-endian length-prefixed UTF-8 JSON frame."""
    if not isinstance(message, Mapping):
        _reject("message_must_be_object")
    validated = _validate_message(dict(message))
    try:
        body = json.dumps(
            validated, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        _reject("message_serialization_failed")
    if not body or len(body) > MAX_FRAME_BYTES:
        _reject("frame_too_large")
    return struct.pack(">I", len(body)) + body


def decode_frame(frame: bytes | bytearray | memoryview) -> dict[str, object]:
    """Decode exactly one bounded frame and validate its complete v1 shape."""
    if not isinstance(frame, (bytes, bytearray, memoryview)):
        _reject("frame_must_be_bytes")
    frame_length = frame.nbytes if isinstance(frame, memoryview) else len(frame)
    if frame_length < 4:
        _reject("truncated_frame_header")
    try:
        data = frame.tobytes() if isinstance(frame, memoryview) else bytes(frame)
    except (TypeError, ValueError):
        _reject("frame_must_be_bytes")
    body_length = struct.unpack(">I", data[:4])[0]
    if body_length == 0:
        _reject("empty_frame")
    if body_length > MAX_FRAME_BYTES:
        _reject("frame_too_large")
    if len(data) != 4 + body_length:
        _reject("frame_length_mismatch")
    try:
        body = data[4:].decode("utf-8", errors="strict")
        message = json.loads(
            body, object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except RunnerProtocolError:
        raise
    except (
        UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError,
        RecursionError,
    ):
        _reject("invalid_json_frame")
    return _validate_message(message)


def validate_correlation(
    message: Mapping[str, object], expected_request_id: str,
) -> None:
    """Reject a valid message that belongs to a different active request."""
    _validate_request_id(expected_request_id)
    if not isinstance(message, Mapping):
        _reject("message_must_be_object")
    validated = _validate_message(dict(message))
    if validated["request_id"] != expected_request_id:
        _reject("request_id_mismatch")
