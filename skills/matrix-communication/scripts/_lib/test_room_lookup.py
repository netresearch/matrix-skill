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
            [
                {
                    "homeserver": "https://m.e",
                    "access_token": "syt_d",
                    "user_id": "@u:e",
                    "timeout": 30,
                    "strict": True,
                }
            ],
        )

    def test_ids_and_full_aliases_pass_without_a_request(self):
        for room in ("!b:e", "#ops:e"):
            with self.subTest(room=room):
                try:
                    resolved = self.resolve(room)
                except room_lookup.RoomLookupError as exc:
                    self.fail(f"{room} was looked up: {exc}")
                else:
                    self.assertEqual(resolved, room)
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

    def test_a_session_without_a_token_is_refused_not_passed_on(self):
        self.session.write_text(json.dumps({"homeserver": "https://m.e"}))
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("ops")
        self.assertIn("no homeserver or access token", str(ctx.exception))
        self.assertEqual(self.configs, [])

    def test_a_write_refuses_a_partial_only_match_and_names_it(self):
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            room_lookup.resolve("Opera", self.env, lister=self.lister, write=True)
        self.assertIn("Operations (#ops:e)", str(ctx.exception))
        self.assertIn("exact name", str(ctx.exception))

    def test_a_read_keeps_the_partial_match(self):
        self.assertEqual(self.resolve("Opera"), "!a:e")

    def test_a_write_takes_an_exact_alias_or_name(self):
        for room, expected in (("ops", "!a:e"), ("#ops", "!a:e"), ("dev chat", "!c:e")):
            with self.subTest(room=room):
                try:
                    resolved = room_lookup.resolve(
                        room, self.env, lister=self.lister, write=True
                    )
                except room_lookup.RoomLookupError as exc:
                    self.fail(f"{room} was refused for a write: {exc}")
                else:
                    self.assertEqual(resolved, expected)

    def test_several_exact_names_are_refused(self):
        self.rooms = [
            {"room_id": "!x:e", "name": "standup", "alias": None},
            {"room_id": "!y:e", "name": "Standup", "alias": None},
        ]
        for write in (False, True):
            with (
                self.subTest(write=write),
                self.assertRaises(room_lookup.RoomLookupError) as ctx,
            ):
                room_lookup.resolve(
                    "standup", self.env, lister=self.lister, write=write
                )
            self.assertIn("several rooms", str(ctx.exception))

    def test_one_alias_name_on_two_servers_is_refused(self):
        self.rooms = [
            {"room_id": "!x:a", "name": "Ops A", "alias": "#ops:a"},
            {"room_id": "!y:b", "name": "Ops B", "alias": "#ops:b"},
        ]
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("ops")
        self.assertIn("by alias", str(ctx.exception))
        self.assertIn("#ops:a", str(ctx.exception))
        self.assertIn("#ops:b", str(ctx.exception))

    def test_one_exact_name_wins_over_rooms_that_contain_it(self):
        # find_room_in_nio_client, which the E2EE scripts of version 4 used,
        # took the single exact name; "test-archive" is no competitor.
        self.rooms = [
            {"room_id": "!t:e", "name": "test", "alias": None},
            {"room_id": "!ta:e", "name": "test-archive", "alias": None},
        ]
        for write in (False, True):
            with self.subTest(write=write):
                try:
                    resolved = room_lookup.resolve(
                        "test", self.env, lister=self.lister, write=write
                    )
                except room_lookup.RoomLookupError as exc:
                    self.fail(f"refused: {exc}")
                else:
                    self.assertEqual(resolved, "!t:e")

    def test_a_listing_that_breaks_is_a_lookup_error(self):
        for error in (ValueError("Expecting value"), TimeoutError("timed out")):

            def lister(config, error=error):
                raise error

            with self.subTest(error=type(error).__name__):
                try:
                    room_lookup.resolve("ops", self.env, lister=lister)
                except room_lookup.RoomLookupError as exc:
                    self.assertIn(str(error), str(exc))
                except Exception as exc:  # noqa: BLE001  # the defect under test
                    self.fail(f"{exc!r} escaped the lookup")
                else:
                    self.fail("a broken listing resolved a room")

    def test_without_a_session_the_room_passes_unchanged(self):
        self.session.unlink()
        self.assertEqual(self.resolve("ops"), "ops")
        self.assertEqual(self.configs, [])


if __name__ == "__main__":
    unittest.main()
