# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib/room_lookup.py`: a room shorthand reaches the room the
scripts of version 4 chose, never matrix-e2ee-cli's own display-name pick.

Run directly (stdlib only; the room list is a fake, and the CLI a script named
by MATRIX_E2EE_CLI; nothing is contacted):

    python3 skills/matrix-communication/scripts/_lib/test_room_lookup.py
"""

import os
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _LIB]
sys.path.insert(0, os.path.dirname(_LIB))

import contextlib
import io
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
        session.write_text(json.dumps({"homeserver": "https://m.e", "user_id": "@u:e"}))
        self.session = session
        self.configs = []
        self.rooms = ROOMS

    def lister(self, env):
        self.configs.append(env)
        return self.rooms

    def resolve(self, room):
        return room_lookup.resolve(room, self.env, lister=self.lister)

    def test_a_bare_name_prefers_the_alias_as_before(self):
        self.assertEqual(self.resolve("ops"), "!a:e")

    def test_a_hash_name_without_server_is_looked_up_as_that_name(self):
        self.assertEqual(self.resolve("#ops"), "!a:e")

    def test_the_lookup_gets_the_commands_environment(self):
        self.resolve("ops")
        self.assertEqual(self.configs, [self.env])

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

    def test_no_joined_room_is_no_match(self):
        self.rooms = []
        with self.assertRaises(room_lookup.RoomLookupError) as ctx:
            self.resolve("ops")
        self.assertIn("no joined room matches", str(ctx.exception))

    def test_the_lookup_reads_no_token_from_the_session(self):
        # The CLI lists the rooms with its own session; the lookup needs none
        # of its fields, so a session without a token is still looked up in.
        self.session.write_text("{}")
        try:
            resolved = self.resolve("ops")
        except room_lookup.RoomLookupError as exc:
            self.fail(f"refused: {exc}")
        self.assertEqual(resolved, "!a:e")

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


FAKE_ROOMS_CLI = """#!{python}
import json, os, sys
with open(os.environ["FAKE_CLI_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
sys.stdout.write(os.environ.get("FAKE_STDOUT", ""))
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class CliRoomsTests(unittest.TestCase):
    """The default lister runs `matrix-e2ee-cli rooms --json`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fake = root / "fake-cli"
        fake.write_text(FAKE_ROOMS_CLI.format(python=sys.executable))
        fake.chmod(0o755)
        self.log = root / "calls.jsonl"
        self.env = {
            "HOME": str(root),
            "XDG_DATA_HOME": str(root / "data"),
            "MATRIX_E2EE_CLI": str(fake),
            "FAKE_CLI_LOG": str(self.log),
            "FAKE_STDOUT": json.dumps(ROOMS),
        }
        session = root / "data" / "matrix-e2ee-cli" / "session.json"
        session.parent.mkdir(parents=True)
        # A homeserver nothing listens on: a lookup over HTTP cannot succeed.
        session.write_text(
            json.dumps({"homeserver": "http://127.0.0.1:9", "access_token": "x"})
        )

    def resolve(self, room, **env):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            try:
                return room_lookup.resolve(room, {**self.env, **env}), stderr, stdout
            except room_lookup.RoomLookupError as exc:
                return exc, stderr, stdout

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_the_rooms_come_from_the_cli(self):
        resolved, _, stdout = self.resolve("ops")
        self.assertEqual(resolved, "!a:e")
        self.assertEqual(self.calls(), [["rooms", "--json"]])
        self.assertEqual(stdout.getvalue(), "", "the room list reached stdout")

    def test_unreadable_members_refuse_the_lookup(self):
        # rooms.rs: a room whose members cannot be read is listed under its
        # room id with this warning; the lookup is refused, as the HTTP one was.
        resolved, _, _ = self.resolve(
            "ops",
            FAKE_STDERR="warning: cannot read the members of !g:e, listed under its "
            "room id: 403 forbidden\n",
        )
        self.assertIsInstance(resolved, room_lookup.RoomLookupError)
        self.assertIn("cannot read the members of !g:e", str(resolved))

    def test_other_warnings_are_passed_on_not_refused(self):
        resolved, stderr, _ = self.resolve(
            "ops", FAKE_STDERR="warning: the daemon answered slowly\n"
        )
        self.assertEqual(resolved, "!a:e")
        self.assertIn("warning: the daemon answered slowly", stderr.getvalue())

    def test_a_failed_listing_is_refused_with_the_clis_error(self):
        resolved, _, _ = self.resolve(
            "ops", FAKE_RC="1", FAKE_STDOUT="", FAKE_STDERR="error: not logged in\n"
        )
        self.assertIsInstance(resolved, room_lookup.RoomLookupError)
        self.assertIn("not logged in", str(resolved))

    def test_output_that_is_no_room_list_is_refused(self):
        for stdout in ("<html>", "{}", "[1]"):
            with self.subTest(stdout=stdout):
                resolved, _, _ = self.resolve("ops", FAKE_STDOUT=stdout)
                self.assertIsInstance(resolved, room_lookup.RoomLookupError)
                self.assertIn("cannot list the joined rooms", str(resolved))


if __name__ == "__main__":
    unittest.main()
