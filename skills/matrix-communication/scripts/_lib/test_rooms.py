# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.rooms`: matrix.to links as ROOM, and matching a search
term against a room of `matrix-e2ee-cli rooms --json`.

Run directly (stdlib only):

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

from _lib import rooms

JANE = "@jane:example.org"
DIRECT = {"room_id": "!dm:e", "name": "Jane Doe", "alias": None, "members": [JANE]}
NAMED = {"room_id": "!n:e", "name": "Jane's notes", "alias": "#notes:e"}


class RoomMatchesTests(unittest.TestCase):
    def test_exact_matches_the_name_or_a_members_user_id(self):
        self.assertTrue(rooms.room_matches(DIRECT, "jane doe", exact=True))
        self.assertTrue(rooms.room_matches(DIRECT, JANE, exact=True))
        self.assertFalse(rooms.room_matches(DIRECT, "jane", exact=True))

    def test_partial_matches_name_alias_and_member(self):
        self.assertTrue(rooms.room_matches(DIRECT, "doe"))
        self.assertTrue(rooms.room_matches(DIRECT, "@jane"))
        self.assertTrue(rooms.room_matches(NAMED, "notes:e"))

    def test_a_named_room_does_not_match_on_members(self):
        self.assertFalse(rooms.room_matches(NAMED, JANE))


class NormalizeRoomInputTests(unittest.TestCase):
    def test_room_permalink_with_via(self):
        link = "https://matrix.to/#/!abc:example.org?via=example.org&via=x.org"
        self.assertEqual(rooms.normalize_room_input(link), "!abc:example.org")

    def test_alias_permalink(self):
        link = "https://matrix.to/#/#ops:example.org"
        self.assertEqual(rooms.normalize_room_input(link), "#ops:example.org")

    def test_percent_encoded_permalink(self):
        link = "https://matrix.to/#/%23ops%3Aexample.org"
        self.assertEqual(rooms.normalize_room_input(link), "#ops:example.org")

    def test_event_permalink_names_its_room(self):
        link = "https://matrix.to/#/!abc:example.org/$ev:example.org?via=example.org"
        self.assertEqual(rooms.normalize_room_input(link), "!abc:example.org")

    def test_other_input_is_unchanged(self):
        for value in ("ops", "#ops:example.org", "!abc:example.org", "Jane Doe"):
            self.assertEqual(rooms.normalize_room_input(value), value)


if __name__ == "__main__":
    unittest.main()
