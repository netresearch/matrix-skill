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
import threading
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
    seen: list

    def do_GET(self):
        self.seen.append((self.path, self.headers.get("Authorization")))
        if self.redirect_to and not self.path.startswith("/done"):
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


class PathSegmentTests(unittest.TestCase):
    """IDs are sent as one encoded path segment."""

    def test_reserved_characters_are_encoded(self):
        self.assertEqual(
            matrix_http.path_segment("!a/b?c#d:srv"), "%21a%2Fb%3Fc%23d%3Asrv"
        )

    def test_room_lookup_sends_the_room_id_as_one_segment(self):
        server, handler = serve()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        sys.path.insert(0, os.path.dirname(HERE))
        self.addCleanup(sys.path.remove, os.path.dirname(HERE))
        from _lib import rooms

        rooms.get_room_info(
            {
                "homeserver": f"http://127.0.0.1:{server.server_address[1]}",
                "access_token": "t",
            },
            "!abc/../../x:example.org",
        )
        self.assertEqual(
            handler.seen[0][0],
            "/_matrix/client/v3/rooms/%21abc%2F..%2F..%2Fx%3Aexample.org/state/m.room.name",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
