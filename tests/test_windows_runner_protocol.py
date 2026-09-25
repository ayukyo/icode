from __future__ import annotations

import base64
import struct
import unittest

from icode.windows_runner_protocol import (
    MAX_FRAME_BYTES,
    RunnerProtocolError,
    decode_frame,
    encode_frame,
    validate_correlation,
)


REQUEST_ID = "0123456789abcdef0123456789abcdef"


def _frame_json(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def _spawn_request(**overrides: object) -> dict[str, object]:
    return {
        "version": 1,
        "type": "spawn_request",
        "request_id": REQUEST_ID,
        "argv": ["python", "-c", "print('ready')"],
        "cwd_rel": "src",
        "timeout_ms": 180_000,
        "output_limit_bytes": 1_048_576,
        **overrides,
    }


class TestWindowsRunnerProtocol(unittest.TestCase):
    def test_spawn_request_uses_big_endian_length_prefixed_json_frame(self) -> None:
        message = _spawn_request()

        frame = encode_frame(message)

        length = struct.unpack(">I", frame[:4])[0]
        self.assertEqual(length, len(frame) - 4)
        self.assertEqual(decode_frame(frame), message)

    def test_accepts_only_the_known_versioned_message_shapes(self) -> None:
        messages = (
            _spawn_request(),
            {"version": 1, "type": "cancel_request", "request_id": REQUEST_ID},
            {"version": 1, "type": "spawn_ready", "request_id": REQUEST_ID},
            {
                "version": 1, "type": "output", "request_id": REQUEST_ID,
                "sequence": 1, "data_b64": "aGVsbG8=",
            },
            {
                "version": 1, "type": "exit", "request_id": REQUEST_ID,
                "exit_code": 0, "timed_out": False,
                "output_truncated": False, "cleanup_ok": True,
            },
            {
                "version": 1, "type": "error", "request_id": REQUEST_ID,
                "stage": "spawn_child", "code": "access_denied",
            },
            {
                "version": 1, "type": "cancel_ack", "request_id": REQUEST_ID,
                "cancelled": True,
            },
        )
        for message in messages:
            with self.subTest(message_type=message["type"]):
                self.assertEqual(decode_frame(encode_frame(message)), message)

    def test_rejects_truncated_trailing_zero_length_and_oversized_frames(self) -> None:
        valid = encode_frame(_spawn_request())
        invalid_frames = (
            valid[:3],
            valid[:-1],
            valid + b"x",
            struct.pack(">I", 0),
            struct.pack(">I", MAX_FRAME_BYTES + 1),
        )
        for frame in invalid_frames:
            with self.subTest(frame_size=len(frame)):
                with self.assertRaises(RunnerProtocolError):
                    decode_frame(frame)

    def test_rejects_unknown_version_type_and_extra_fields(self) -> None:
        invalid = (
            _spawn_request(version=2),
            _spawn_request(version=True),
            _spawn_request(type="arbitrary"),
            _spawn_request(environment={"PATH": "attacker-controlled"}),
            _spawn_request(policy={"network_mode": "proxy_allowlist"}),
            _spawn_request(acl={"grant": "outside-workspace"}),
            _spawn_request(token="caller-controlled"),
            _spawn_request(wfp={"allow": "any"}),
        )
        for message in invalid:
            with self.subTest(message=message):
                with self.assertRaises(RunnerProtocolError):
                    encode_frame(message)

    def test_rejects_malformed_json_duplicate_keys_and_nonstandard_constants(self) -> None:
        bodies = (
            b"{",
            b'{"version":1,"version":1}',
            b'{"version":NaN}',
            b'{"version":"\\ud800"}',
            b"\xff",
            b"[" * 2_000 + b"0" + b"]" * 2_000,
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(RunnerProtocolError):
                    decode_frame(_frame_json(body))

    def test_spawn_request_rejects_bad_argv_timeout_and_output_limit(self) -> None:
        invalid = (
            _spawn_request(argv=[]),
            _spawn_request(argv="python -c pass"),
            _spawn_request(argv=["python", 7]),
            _spawn_request(argv=["\t", "arg"]),
            _spawn_request(argv=["python", "nul\x00value"]),
            _spawn_request(argv=["python", "\ud800"]),
            _spawn_request(argv=["python", "x" * (MAX_FRAME_BYTES + 1)]),
            _spawn_request(timeout_ms=True),
            _spawn_request(timeout_ms=0),
            _spawn_request(timeout_ms=-1),
            _spawn_request(timeout_ms=2**32),
            _spawn_request(output_limit_bytes=False),
            _spawn_request(output_limit_bytes=0),
            _spawn_request(output_limit_bytes=2**32),
        )
        for message in invalid:
            with self.subTest(message=message):
                with self.assertRaises(RunnerProtocolError):
                    encode_frame(message)

    def test_cwd_must_be_canonical_workspace_relative_posix_path(self) -> None:
        invalid_paths = (
            "",
            "/etc",
            "../outside",
            "src/../../outside",
            "src\\..\\outside",
            "C:/Windows",
            "//server/share",
            "src//nested",
            "./src",
            "src/",
            "src/\x01control",
        )
        for cwd in invalid_paths:
            with self.subTest(cwd=cwd):
                with self.assertRaises(RunnerProtocolError):
                    encode_frame(_spawn_request(cwd_rel=cwd))
        self.assertEqual(
            decode_frame(encode_frame(_spawn_request(cwd_rel="."))) ["cwd_rel"],
            ".",
        )

    def test_output_messages_require_bounded_canonical_base64_and_sequence(self) -> None:
        message = {
            "version": 1, "type": "output", "request_id": REQUEST_ID,
            "sequence": 1, "data_b64": "aGVsbG8=",
        }
        self.assertEqual(decode_frame(encode_frame(message)), message)
        invalid = (
            {**message, "sequence": True},
            {**message, "sequence": -1},
            {**message, "data_b64": "aGVsbG8"},
            {**message, "data_b64": "!!!!"},
            {**message, "data_b64": ""},
            {
                **message,
                "data_b64": base64.b64encode(
                    b"x" * (32 * 1024 + 1),
                ).decode("ascii"),
            },
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate.get("sequence")):
                with self.assertRaises(RunnerProtocolError):
                    encode_frame(candidate)

    def test_exit_and_error_messages_reject_ambiguous_or_unbounded_results(self) -> None:
        exit_message = {
            "version": 1, "type": "exit", "request_id": REQUEST_ID,
            "exit_code": 0, "timed_out": False,
            "output_truncated": False, "cleanup_ok": True,
        }
        error_message = {
            "version": 1, "type": "error", "request_id": REQUEST_ID,
            "stage": "spawn_child", "code": "access_denied",
        }
        self.assertEqual(decode_frame(encode_frame(exit_message)), exit_message)
        self.assertEqual(decode_frame(encode_frame(error_message)), error_message)
        invalid = (
            {**exit_message, "exit_code": True},
            {**exit_message, "cleanup_ok": 1},
            {**error_message, "stage": "arbitrary", "code": "access_denied"},
            {**error_message, "stage": [], "code": "access_denied"},
            {**error_message, "stage": "spawn_child", "code": {}},
            {**error_message, "stage": "spawn_child", "code": "details: secret"},
            {**error_message, "debug_message": "do not serialize arbitrary details"},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(RunnerProtocolError):
                    encode_frame(candidate)

    def test_response_correlation_must_match_active_request(self) -> None:
        message = {"version": 1, "type": "spawn_ready", "request_id": REQUEST_ID}
        validate_correlation(message, REQUEST_ID)
        with self.assertRaises(RunnerProtocolError):
            validate_correlation(message, "f" * 32)
        with self.assertRaises(RunnerProtocolError):
            validate_correlation(message, "not-an-id")
        with self.assertRaises(RunnerProtocolError):
            validate_correlation("not an object", REQUEST_ID)  # type: ignore[arg-type]

    def test_decoder_rejects_non_object_json_and_invalid_frame_types(self) -> None:
        for body in (b"[]", b"null", b"1", b'"text"'):
            with self.subTest(body=body):
                with self.assertRaises(RunnerProtocolError):
                    decode_frame(_frame_json(body))
        with self.assertRaises(RunnerProtocolError):
            decode_frame("not bytes")  # type: ignore[arg-type]

    def test_decoder_accepts_byte_view_without_changing_frame_semantics(self) -> None:
        frame = encode_frame(_spawn_request())
        self.assertEqual(decode_frame(memoryview(frame)), _spawn_request())


if __name__ == "__main__":
    unittest.main()
