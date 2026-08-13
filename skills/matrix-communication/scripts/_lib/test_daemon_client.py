"""Tests for `_lib.daemon_client`.

The point under test is the routing decision: a command may only delegate to a
daemon that actually answers. Deciding on the store lock instead would be wrong
in a way that is easy to miss - a direct send holds that same lock for its
couple of seconds.

Run directly: python3 skills/matrix-communication/scripts/_lib/test_daemon_client.py
"""

import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import daemon_client
from daemon_client import daemon_request


class FakeDaemon:
    """One-shot listener answering with a canned payload."""

    def __init__(self, path, response, reply=True):
        self.path = str(path)
        self.response = response
        self.reply = reply
        self.received = None
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            self.received = json.loads(data)
            if self.reply:
                conn.sendall(json.dumps(self.response).encode() + b"\n")

    def close(self):
        self.sock.close()


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / "daemon.sock"
        real = daemon_client.socket_path
        daemon_client.socket_path = lambda: self.path
        self.addCleanup(setattr, daemon_client, "socket_path", real)

    def test_no_socket_file_means_no_daemon(self):
        self.assertIsNone(daemon_request({"op": "status"}))

    def test_stale_socket_means_no_daemon(self):
        """A crashed daemon leaves the file behind with nothing listening. The
        caller must fall back, not hang or crash."""
        self.path.touch()
        self.assertIsNone(daemon_request({"op": "status"}))

    def test_request_round_trips(self):
        fake = FakeDaemon(self.path, {"ok": True, "event_id": "$x"})
        self.addCleanup(fake.close)
        got = daemon_request({"op": "send", "room": "!r:e", "body": "hi"})
        self.assertEqual(got, {"ok": True, "event_id": "$x"})
        fake.thread.join(timeout=5)
        self.assertEqual(fake.received["op"], "send")
        self.assertEqual(fake.received["body"], "hi")

    def test_error_response_is_returned_not_swallowed(self):
        """An error from the daemon is an answer. Returning None would send the
        caller down the direct path and send the message twice."""
        fake = FakeDaemon(self.path, {"ok": False, "error": "no such room"})
        self.addCleanup(fake.close)
        got = daemon_request({"op": "send", "room": "!r:e", "body": "hi"})
        self.assertIsNotNone(got)
        self.assertFalse(got["ok"])
        self.assertIn("no such room", got["error"])

    def test_daemon_closing_without_answering_reads_as_no_daemon(self):
        fake = FakeDaemon(self.path, {}, reply=False)
        self.addCleanup(fake.close)
        self.assertIsNone(daemon_request({"op": "status"}))

    def test_unicode_survives_the_round_trip(self):
        fake = FakeDaemon(self.path, {"ok": True, "event_id": "$x"})
        self.addCleanup(fake.close)
        daemon_request({"op": "send", "room": "!r:e", "body": "Grüße 🎁"})
        fake.thread.join(timeout=5)
        self.assertEqual(fake.received["body"], "Grüße 🎁")


class SocketPathTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get("XDG_RUNTIME_DIR")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.previous is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self.previous

    def test_an_existing_runtime_dir_is_preferred(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        os.environ["XDG_RUNTIME_DIR"] = directory
        self.assertEqual(
            str(daemon_client.socket_path()),
            f"{directory}/matrix-skill/daemon.sock",
        )

    def test_a_runtime_dir_that_does_not_exist_is_not_used(self):
        """WSL and containers export XDG_RUNTIME_DIR for a directory nobody
        created. Trusting the variable crashed the daemon on startup."""
        os.environ["XDG_RUNTIME_DIR"] = "/run/user/does-not-exist-99999"
        path = daemon_client.socket_path()
        self.assertNotIn("does-not-exist", str(path))
        self.assertTrue(str(path).endswith("matrix-skill/daemon.sock"))

    def test_falls_back_when_there_is_no_runtime_dir(self):
        os.environ.pop("XDG_RUNTIME_DIR", None)
        self.assertTrue(str(daemon_client.socket_path()).endswith("daemon.sock"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
