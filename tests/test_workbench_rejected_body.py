"""Rejected POST transport hygiene, independent of authorization outcomes."""

from __future__ import annotations

from email.message import Message
import http.client
import io
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from icode.workbench import (
    MAX_REJECTED_BODY_DRAIN_BYTES, WorkbenchRequestHandler, WorkbenchServer,
)
from tests._support import require_skill, temp_workspace
from tests.test_workbench import HTTP_TEST_TIMEOUT_SECONDS, _request


class TestRejectedPostBody(unittest.TestCase):
    def _handler(self, *, path="/api/v1/tickets/test/intents", cookie=True,
                 origin=None, content_type="application/json", length=None,
                 body=b'{"intent":"start","request_id":"deny"}'):
        handler = object.__new__(WorkbenchRequestHandler)
        handler.command = "POST"
        handler.path = path
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1"
        handler.headers["Content-Type"] = content_type
        handler.headers["Content-Length"] = str(len(body)) if length is None else length
        if cookie:
            handler.headers["Cookie"] = "icode_workbench_session=trusted"
        if origin:
            handler.headers["Origin"] = origin
        handler.rfile = io.BytesIO(body)
        handler.connection = Mock()
        handler.connection.gettimeout.return_value = None
        handler.server = SimpleNamespace(session_token="trusted", service=Mock(), autonomy=Mock())
        responses = []
        handler._send_bytes = lambda status, payload, content_type: responses.append(
            (status, json.loads(payload), handler.rfile.tell()))
        return handler, responses

    def test_early_rejections_discard_complete_bounded_body_before_response(self):
        cases = (
            ({"cookie": False}, 403),
            ({"origin": "https://evil.example.com"}, 403),
            ({"path": "/unknown"}, 404),
            ({"content_type": "text/plain"}, 415),
            ({"host": "evil.example.com"}, 403),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                options = dict(options)
                host = options.pop("host", None)
                handler, responses = self._handler(**options)
                if host:
                    handler.headers.replace_header("Host", host)
                handler.do_POST()
                self.assertEqual(responses[0][0], expected)
                self.assertEqual(responses[0][2], len(handler.rfile.getvalue()))
                handler.server.service.create_ticket.assert_not_called()
                handler.server.autonomy.handle_intent.assert_not_called()
                handler.connection.settimeout.assert_called()
                self.assertIsNone(handler.connection.settimeout.call_args.args[0])

    def test_body_already_read_does_not_start_another_drain(self):
        handler, responses = self._handler(path="/api/v1/tickets/bad%2Fid/intents")
        with patch.object(handler, "_drain_rejected_body", wraps=handler._drain_rejected_body) as drain:
            handler.do_POST()
        self.assertEqual(responses[0][0], 400)
        self.assertEqual(responses[0][1]["code"], "invalid_ticket_id")
        drain.assert_not_called()

    def test_unknown_or_ambiguous_framing_is_not_read_to_find_a_boundary(self):
        for mode in ("invalid", "negative", "zero", "oversize", "duplicate", "chunked", "missing"):
            with self.subTest(mode=mode):
                lengths = {"invalid": "invalid", "negative": "-1", "zero": "0",
                           "oversize": str(MAX_REJECTED_BODY_DRAIN_BYTES + 1)}
                handler, responses = self._handler(cookie=False, length=lengths.get(mode))
                if mode == "duplicate":
                    handler.headers["Content-Length"] = "999"
                if mode == "chunked":
                    handler.headers["Transfer-Encoding"] = "chunked"
                if mode == "missing":
                    del handler.headers["Content-Length"]
                handler.do_POST()
                self.assertEqual(responses[0][0], 403)
                self.assertEqual(responses[0][2], 0)
                handler.connection.settimeout.assert_not_called()

    def test_incomplete_body_timeout_keeps_refusal_and_restores_timeout(self):
        handler, responses = self._handler(cookie=False)
        handler.rfile = Mock()
        handler.rfile.read1.side_effect = TimeoutError("slow client")
        handler.rfile.tell.return_value = 0
        handler.do_POST()
        self.assertEqual(responses[0][0], 403)
        handler.rfile.read1.assert_called_once()
        self.assertIsNone(handler.connection.settimeout.call_args.args[0])
        handler.server.autonomy.handle_intent.assert_not_called()

    def test_rejected_length_uses_ascii_digits_and_http_optional_whitespace(self):
        for value in ("+38", "3_8", "３８", "٣٨", "\v38", "38\r"):
            with self.subTest(invalid=value):
                handler, responses = self._handler(cookie=False, body=b"x" * 38, length=value)
                handler.do_POST()
                self.assertEqual(responses[0][0], 403)
                self.assertEqual(responses[0][2], 0)
                handler.connection.settimeout.assert_not_called()
                handler.server.service.create_ticket.assert_not_called()
                handler.server.autonomy.handle_intent.assert_not_called()
        for value in ("38", "038", " 38 ", "\t38\t"):
            with self.subTest(valid=value):
                handler, responses = self._handler(cookie=False, body=b"x" * 38, length=value)
                handler.do_POST()
                self.assertEqual(responses[0][0], 403)
                self.assertEqual(responses[0][2], 38)
                self.assertIsNone(handler.connection.settimeout.call_args.args[0])
                handler.server.service.create_ticket.assert_not_called()
                handler.server.autonomy.handle_intent.assert_not_called()

    def test_oversize_body_drains_only_once_on_the_existing_413_path(self):
        body = b"x" * (64 * 1024 + 1)
        handler, responses = self._handler(body=body)
        with patch.object(handler, "_drain_rejected_body", wraps=handler._drain_rejected_body) as drain:
            handler.do_POST()
        self.assertEqual(responses[0][0], 413)
        self.assertEqual(responses[0][2], len(body))
        drain.assert_called_once_with(len(body))

    def test_get_refusal_never_reads_a_declared_request_body(self):
        handler, responses = self._handler(cookie=False)
        handler.command = "GET"
        handler.path = "/api/v1/bootstrap"
        handler.do_GET()
        self.assertEqual(responses[0][0], 403)
        self.assertEqual(responses[0][2], 0)
        handler.connection.settimeout.assert_not_called()

    def test_second_error_never_retries_a_partial_discard(self):
        handler, responses = self._handler(cookie=False)
        handler.rfile = Mock()
        handler.rfile.read1.side_effect = TimeoutError("slow client")
        handler.rfile.tell.return_value = 0
        handler.do_POST()
        handler._error(403, "forbidden", "still denied")
        self.assertEqual(len(responses), 2)
        handler.rfile.read1.assert_called_once()

    def test_read_or_drain_interruptions_keep_identity_and_do_not_retry_io(self):
        for error in (OSError("read failure"), KeyboardInterrupt("stop"), SystemExit(17)):
            with self.subTest(error=type(error).__name__):
                handler, responses = self._handler()
                handler.rfile = Mock()
                handler.rfile.read.side_effect = error
                handler.rfile.tell.return_value = 0
                with self.assertRaises(type(error)) as raised:
                    handler._read_json()
                self.assertIs(raised.exception, error)
                handler._error(400, "invalid_request", "denied")
                self.assertEqual(responses[0][0], 400)
                handler.rfile.read.assert_called_once()
                handler.rfile.read1.assert_not_called()
        for error in (KeyboardInterrupt("stop"), SystemExit(17)):
            with self.subTest(drain_error=type(error).__name__):
                handler, responses = self._handler(cookie=False)
                handler.rfile = Mock()
                handler.rfile.read1.side_effect = error
                handler.rfile.tell.return_value = 0
                with self.assertRaises(type(error)) as raised:
                    handler.do_POST()
                self.assertIs(raised.exception, error)
                self.assertFalse(responses)
                self.assertIsNone(handler.connection.settimeout.call_args.args[0])


class TestRejectedPostTransport(unittest.TestCase):
    def test_real_http_complete_early_refusals_consume_bytes_without_business_calls(self):
        observations = []
        original = WorkbenchRequestHandler._drain_rejected_body

        def observed(handler, length):
            reader = handler.rfile
            chunks = []
            def read1(limit):
                chunk = reader.read1(limit)
                chunks.append(len(chunk))
                return chunk
            handler.rfile = SimpleNamespace(read1=read1)
            try:
                original(handler, length)
            finally:
                handler.rfile = reader
            observations.append((length, sum(chunks)))

        with temp_workspace() as workspace:
            server = WorkbenchServer(settings=require_skill(), workspace=workspace,
                                     index_path=workspace / "index.json", port=0)
            url = server.start()
            try:
                _, headers, _ = _request(url)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                payload = {"intent": "start", "request_id": "cross-origin"}
                length = len(json.dumps(payload).encode("utf-8"))
                cases = (
                    ("api/v1/tickets/test/intents", None, None, "application/json", 403),
                    ("api/v1/tickets/test/intents", cookie, "https://evil.example.com", "application/json", 403),
                    ("unknown", cookie, None, "application/json", 404),
                    ("api/v1/tickets", cookie, None, "text/plain", 415),
                )
                with patch.object(WorkbenchRequestHandler, "_drain_rejected_body", observed), \
                     patch.object(server.service, "create_ticket") as create, \
                     patch.object(server.autonomy, "handle_intent") as intent:
                    for path, selected_cookie, origin, content_type, expected in cases:
                        status, _, body = _request(url + path, method="POST", payload=payload,
                            cookie=selected_cookie, origin=origin, content_type=content_type)
                        self.assertEqual(status, expected)
                        self.assertFalse(json.loads(body)["ok"])
                    create.assert_not_called()
                    intent.assert_not_called()
                self.assertEqual(observations, [(length, length)] * len(cases))
            finally:
                server.stop()

    def test_real_http_header_only_rejected_client_does_not_wait_for_the_body(self):
        with temp_workspace() as workspace:
            server = WorkbenchServer(settings=require_skill(), workspace=workspace,
                                     index_path=workspace / "index.json", port=0)
            server.start()
            connection = http.client.HTTPConnection(*server.httpd.server_address,
                                                    timeout=HTTP_TEST_TIMEOUT_SECONDS)
            try:
                started = time.monotonic()
                connection.putrequest("POST", "/api/v1/tickets/test/intents")
                connection.putheader("Content-Length", "38")
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                self.assertEqual(json.loads(response.read())["code"], "forbidden")
                self.assertLess(time.monotonic() - started, 2)
            finally:
                connection.close()
                server.stop()


if __name__ == "__main__":
    unittest.main()
