# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/room_lookup.py`: a room shorthand reaches the room the
scripts of version 4 chose, never matrix-e2ee-cli's own display-name pick.

Run directly (stdlib only; the room list is a fake, nothing is contacted):

    python3 skills/matrix-communication/scripts/_lib/test_room_lookup.py
"""

import os
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _LIB]
sys.path.insert(0, os.path.dirname(_LIB))

import json
import tempfile
import unittest
from pathlib import Path

from _lib import room_lookup

# Room A has the alias #ops:e and its own name; room B is *named* "ops". The
# old scripts sent "ops" and "#ops" to A (alias before name); the CLI alone
# would pick B by its display name.
ROOMS = [
    {"room_id": "!a:e", "name": "Operations", "alias": "#ops:e"},
    {"room_id": "!b:e", "name": "ops", "alias": None},
    {"room_id": "!c:e", "name": "dev chat", "alias": None},
    {"room_id": "!d:e", "name": "dev talk", "alias": None},
]


class ResolveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env = {"HOME": tmp.name, "XDG_DATA_HOME": os.path.join(tmp.name, "data")}
        session = Path(self.env["XDG_DATA_HOME"], "matrix-e2ee-cli", "session.json")
        session.parent.mkdir(parents=True)
        session.write_text(
            json.dumps(
                {
                    "homeserver": "https://m.e",
                    "user_id": "@u:e",
                    "access_token": "syt_d",
                }
            )
        )
        self.session = session
        self.configs = []
        self.rooms = ROOMS

    def lister(self, config):
        self.configs.append(config)
        return self.rooms

    def resolve(self, room):
        return room_lookup.resolve(room, self.env, lister=self.lister)

    def test_a_bare_name_prefers_the_alias_as_before(self):
        self.assertEqual(self.resolve("ops"), "!a:e")

    def test_a_hash_name_without_server_is_looked_up_as_that_name(self):
        self.assertEqual(self.resolve("#ops"), "!a:e")

    def test_the_lookup_uses_the_session_of_the_skills_own_device(self):
        self.resolve("ops")
        self.assertEqual(
            self.configs,
            [{"homeserver": "https://m.e", "access_token": "syt_d", "user_id": "@u:e"}],
        )

    def test_ids_and_full_aliases_pass_without_a_request(self):
        for room in ("!b:e", "#ops:e"):
            with self.subTest(room=room):
                self.assertEqual(self.resolve(room), room)
        self.assertEqual(self.configs, [])

    def test_an_ambiguous_name_is_refused(self):
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("dev")
        self.assertIn("several rooms", str(ctx.exception))

    def test_no_match_is_refused(self):
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("nowhere")
        self.assertIn("no joined room matches", str(ctx.exception))

    def test_rooms_that_cannot_be_listed_are_refused_not_guessed(self):
        self.rooms = []
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("ops")
        self.assertIn("cannot list the joined rooms", str(ctx.exception))

    def test_without_a_session_the_room_passes_unchanged(self):
        self.session.unlink()
        self.assertEqual(self.resolve("ops"), "ops")
        self.assertEqual(self.configs, [])


if __name__ == "__main__":
    unittest.main()
