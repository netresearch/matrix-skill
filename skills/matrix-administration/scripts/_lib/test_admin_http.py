# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/admin_http.py`: the token stays with the homeserver's origin.

Run directly (stdlib only):

    python3 skills/matrix-administration/scripts/_lib/test_admin_http.py
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import admin_http


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
        result = admin_http.admin_request(
            {"homeserver": home_url, "admin_token": "SECRET"}, "GET", "/v1/rooms"
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(home.seen[0][1], "Bearer SECRET")
        self.assertEqual(other.seen, [("/done", None)])

    def test_token_kept_on_same_origin_redirect(self):
        home_url, home = self.start()
        home.redirect_to = f"{home_url}/done"
        admin_http.admin_request(
            {"homeserver": home_url, "admin_token": "SECRET"}, "GET", "/v1/rooms"
        )
        self.assertEqual(
            [auth for _, auth in home.seen], ["Bearer SECRET", "Bearer SECRET"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
