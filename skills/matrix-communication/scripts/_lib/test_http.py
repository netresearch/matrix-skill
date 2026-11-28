# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/http.py`: the access token stays with the homeserver's origin.

Run directly (stdlib only):

    python3 skills/matrix-communication/scripts/_lib/test_http.py

Running this file puts its own directory first on sys.path, where `http.py`
would shadow the stdlib `http` package. The directory is removed before any
stdlib import and the module under test is loaded from its path instead.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

_spec = importlib.util.spec_from_file_location(
    "matrix_http", os.path.join(HERE, "http.py")
)
matrix_http = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matrix_http)


class Recorder(BaseHTTPRequestHandler):
    """Answers with a redirect when `redirect_to` is set, else with JSON."""

    redirect_to = None
    delay = 0
    status = 200
    payload = None  # JSON to answer with instead of {"ok": true}
    truncate = False  # promise more bytes than are sent
    raw = None  # bytes to answer with as they are
    body_delay = 0  # seconds between the headers and the body
    hangup = False  # close the connection without answering
    seen: list

    def do_GET(self):
        self.seen.append((self.path, self.headers.get("Authorization")))
        if self.hangup:
            self.close_connection = True
            return
        if self.delay:
            time.sleep(self.delay)
        if self.redirect_to and not self.path.startswith("/done"):
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        body = (
            self.raw
            if self.raw is not None
            else b"null"
            if self.payload == "__null__"
            else json.dumps(
                {"ok": True} if self.payload is None else self.payload
            ).encode()
        )
        try:
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header(
                "Content-Length", str(len(body) + (50 if self.truncate else 0))
            )
            self.end_headers()
            if self.body_delay:
                self.wfile.flush()
                time.sleep(self.body_delay)
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client gave up (TimeoutTests)

    def log_message(self, *args):
        pass


def serve(redirect_to=None):
    handler = type("H", (Recorder,), {"redirect_to": redirect_to, "seen": []})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, handler


class RedirectAuthorizationTests(unittest.TestCase):
    def start(self, redirect_to=None):
        server, handler = serve(redirect_to)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}", handler

    def test_token_not_sent_to_another_origin_after_redirect(self):
        other_url, other = self.start()
        home_url, home = self.start(redirect_to=f"{other_url}/done")
        result = matrix_http.matrix_request(
            {"homeserver": home_url, "access_token": "SECRET"}, "GET", "/joined_rooms"
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(home.seen[0][1], "Bearer SECRET")
        self.assertEqual(other.seen, [("/done", None)])

    def test_token_kept_on_same_origin_redirect(self):
        home_url, home = self.start()
        home.redirect_to = f"{home_url}/done"
        matrix_http.matrix_request(
            {"homeserver": home_url, "access_token": "SECRET"}, "GET", "/joined_rooms"
        )
        self.assertEqual(
            [auth for _, auth in home.seen], ["Bearer SECRET", "Bearer SECRET"]
        )


class SocketTimeoutTests(unittest.TestCase):
    """matrix-doctor.py bounds a request with the socket default timeout."""

    def setUp(self):
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(0.3)
        self.addCleanup(socket.setdefaulttimeout, old)

    def start(self, **attrs):
        server, handler = serve()
        for name, value in attrs.items():
            setattr(handler, name, value)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return {
            "homeserver": f"http://127.0.0.1:{server.server_address[1]}",
            "access_token": "t",
        }

    def test_a_slow_server_is_given_up_on(self):
        config = self.start(delay=1.0)
        started = time.monotonic()
        result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        self.assertLess(time.monotonic() - started, 0.9)
        self.assertIn("error", result)

    def test_a_timeout_while_reading_the_error_body_is_an_error_dict(self):
        config = self.start(status=502, payload={"error": "bad"}, body_delay=1.0)
        try:
            result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        except Exception as exc:  # noqa: BLE001  # the defect under test
            self.fail(f"{exc!r} escaped")
        else:
            self.assertEqual(result["errcode"], "502")
            self.assertIn("broken body", result["error"])


class HangupTests(unittest.TestCase):
    """A server that closes the connection without answering."""

    def test_a_closed_connection_is_an_error_dict(self):
        server, handler = serve()
        handler.hangup = True
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = {
            "homeserver": f"http://127.0.0.1:{server.server_address[1]}",
            "access_token": "t",
        }
        try:
            result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        except Exception as exc:  # noqa: BLE001 - the regression is any raise
            self.fail(f"a closed connection raised {exc!r}")
        else:
            self.assertIn("error", result)


class ErrorBodyTests(unittest.TestCase):
    """Error answers whose body is not a JSON object, or is cut off."""

    start = SocketTimeoutTests.start

    def test_an_error_status_is_an_error_dict(self):
        config = self.start(status=502, payload={"error": "bad gateway"})
        result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        self.assertEqual(result["error"], "bad gateway")

    def test_a_cut_off_error_body_is_an_error_dict(self):
        config = self.start(status=502, payload={"error": "bad"}, truncate=True)
        try:
            result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        except Exception as exc:  # noqa: BLE001  # the defect under test
            self.fail(f"{exc!r} escaped")
        else:
            self.assertEqual(result["errcode"], "502")
            self.assertIn("broken body", result["error"])

    def test_an_error_body_that_is_not_an_object_falls_back_to_the_raw_body(self):
        # "__null__" makes the recorder send the JSON literal null.
        for payload in ([], "__null__", "text"):
            with self.subTest(payload=payload):
                config = self.start(status=500, payload=payload)
                try:
                    result = matrix_http.matrix_request(
                        config, "GET", "/account/whoami"
                    )
                except Exception as exc:  # noqa: BLE001  # the defect under test
                    self.fail(f"{exc!r} escaped")
                else:
                    self.assertEqual(result["errcode"], "500")

    def test_an_error_body_that_is_not_utf8_is_read_with_replacements(self):
        config = self.start(status=502, raw=b'{"error": "bad \xff gateway"}')
        try:
            result = matrix_http.matrix_request(config, "GET", "/account/whoami")
        except Exception as exc:  # noqa: BLE001  # the defect under test
            self.fail(f"{exc!r} escaped")
        else:
            self.assertEqual(result["error"], "bad \ufffd gateway")


if __name__ == "__main__":
    unittest.main(verbosity=2)
