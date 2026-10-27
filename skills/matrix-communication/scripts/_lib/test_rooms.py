# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.rooms.find_direct_room`: which room `--to` sends to.

Run directly (stdlib only, no nio):

    python3 skills/matrix-communication/scripts/_lib/test_rooms.py

Running this file puts its own directory first on sys.path, where `http.py`
would shadow the stdlib `http` package; it is swapped for the scripts
directory so `_lib` is imported as a package.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]
sys.path.insert(0, os.path.dirname(HERE))

import unittest
from unittest import mock

from _lib import rooms

ME = "@me:example.org"
JANE = "@jane:example.org"
CONFIG = {"homeserver": "https://example.org", "user_id": ME, "access_token": "t"}


def fake_server(direct, joined, membership):
    """Answer matrix_request from fixed m.direct, joined rooms and memberships."""

    def request(config, method, endpoint, data=None):
        if endpoint.endswith("/account_data/m.direct"):
            return direct
        if endpoint == "/joined_rooms":
            return {"joined_rooms": joined}
        for room_id, state in membership.items():
            if rooms.path_segment(room_id) in endpoint:
                return {"membership": state}
        return {"error": "Not found", "errcode": "M_NOT_FOUND"}

    return request


class FindDirectRoomTests(unittest.TestCase):
    def find(self, direct, joined, membership):
        with mock.patch.object(
            rooms, "matrix_request", fake_server(direct, joined, membership)
        ):
            return rooms.find_direct_room(CONFIG, JANE)

    def test_single_joined_direct_room_is_returned(self):
        room = self.find({JANE: ["!a:x"]}, ["!a:x"], {"!a:x": "join"})
        self.assertEqual(room, "!a:x")

    def test_invited_partner_counts(self):
        room = self.find({JANE: ["!a:x"]}, ["!a:x"], {"!a:x": "invite"})
        self.assertEqual(room, "!a:x")

    def test_room_this_account_left_is_skipped(self):
        """m.direct keeps rooms after a leave; such a room cannot be sent to."""
        room = self.find(
            {JANE: ["!old:x", "!new:x"]},
            ["!new:x"],
            {"!old:x": "join", "!new:x": "join"},
        )
        self.assertEqual(room, "!new:x")

    def test_room_the_partner_left_is_skipped(self):
        with self.assertRaisesRegex(ValueError, "left each of them"):
            self.find({JANE: ["!a:x"]}, ["!a:x"], {"!a:x": "leave"})

    def test_only_left_rooms_is_an_error_naming_them(self):
        with self.assertRaisesRegex(ValueError, "!gone:x"):
            self.find({JANE: ["!gone:x"]}, [], {})

    def test_no_direct_chat_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "No direct chat"):
            self.find({"@other:x": ["!a:x"]}, ["!a:x"], {"!a:x": "join"})

    def test_missing_m_direct_is_no_direct_chat(self):
        missing = {"error": "Account data not found", "errcode": "M_NOT_FOUND"}
        with self.assertRaisesRegex(ValueError, "No direct chat"):
            self.find(missing, [], {})

    def test_unreadable_m_direct_is_reported(self):
        denied = {"error": "Invalid token", "errcode": "M_UNKNOWN_TOKEN"}
        with self.assertRaisesRegex(ValueError, "Could not read m.direct"):
            self.find(denied, [], {})

    def test_several_usable_rooms_are_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "Several direct chats"):
            self.find(
                {JANE: ["!a:x", "!b:x"]},
                ["!a:x", "!b:x"],
                {"!a:x": "join", "!b:x": "join"},
            )


if __name__ == "__main__":
    unittest.main()
