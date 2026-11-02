# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for `_lib.rooms`: how a ROOM argument finds its room.

`find_direct_room` decides which room `--to` sends to; the rest covers
names for rooms without m.room.name (direct chats), matching on them on the
HTTP and the nio path, and matrix.to links as ROOM.

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
import unittest.mock

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
        with unittest.mock.patch.object(
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


def member(user_id, displayname=None, membership="join"):
    content = {"membership": membership}
    if displayname:
        content["displayname"] = displayname
    return {"type": "m.room.member", "state_key": user_id, "content": content}


def fake_rooms_server(rooms_state):
    """Answer matrix_request for list_joined_rooms().

    rooms_state maps room ID -> {"name": ..., "alias": ..., "members": [...]};
    a missing name/alias is answered with M_NOT_FOUND like Synapse does, and
    "members" set to None makes the member request fail.
    """
    not_found = {"error": "Event not found", "errcode": "M_NOT_FOUND"}
    calls = []

    def request(config, method, endpoint, data=None):
        calls.append(endpoint)
        if endpoint == "/joined_rooms":
            return {"joined_rooms": list(rooms_state)}
        for room_id, state in rooms_state.items():
            prefix = f"/rooms/{rooms.path_segment(room_id)}/"
            if not endpoint.startswith(prefix):
                continue
            rest = endpoint[len(prefix) :]
            if rest == "state/m.room.name":
                return {"name": state["name"]} if state.get("name") else not_found
            if rest == "state/m.room.canonical_alias":
                return {"alias": state["alias"]} if state.get("alias") else not_found
            if rest == "members?not_membership=leave":
                if state.get("members") is None:
                    return {"error": "Forbidden", "errcode": "M_FORBIDDEN"}
                return {"chunk": state["members"]}
        return not_found

    request.calls = calls
    return request


DM = "!dm:x"
GROUP = "!group:x"
OPS = "!ops:x"
STATE = {
    DM: {"members": [member(ME, "Me"), member(JANE, "Jane Doe")]},
    GROUP: {
        "members": [
            member(ME, "Me"),
            member(JANE, "Jane Doe"),
            member("@max:example.org", "Max Mustermann"),
        ]
    },
    OPS: {"name": "Ops", "alias": "#ops:example.org", "members": []},
}


class RoomNameTests(unittest.TestCase):
    def list_rooms(self, state):
        server = fake_rooms_server(state)
        with unittest.mock.patch.object(rooms, "matrix_request", server):
            return {r["room_id"]: r for r in rooms.list_joined_rooms(CONFIG)}, server

    def test_direct_chat_is_named_after_the_other_person(self):
        listed, _ = self.list_rooms(STATE)
        self.assertEqual(listed[DM]["name"], "Jane Doe")
        self.assertEqual(listed[DM]["members"], [JANE])

    def test_invited_partner_names_the_room(self):
        state = {DM: {"members": [member(ME), member(JANE, "Jane", "invite")]}}
        listed, _ = self.list_rooms(state)
        self.assertEqual(listed[DM]["name"], "Jane")

    def test_left_member_does_not_name_the_room(self):
        state = {DM: {"members": [member(ME), member(JANE, "Jane", "leave")]}}
        listed, _ = self.list_rooms(state)
        self.assertEqual(listed[DM]["name"], "Empty Room")

    def test_member_without_display_name_is_named_by_user_id(self):
        state = {DM: {"members": [member(ME), member(JANE)]}}
        listed, _ = self.list_rooms(state)
        self.assertEqual(listed[DM]["name"], JANE)

    def test_display_name_shared_with_this_account_is_qualified(self):
        """nio's user_name() adds the user ID when two members share a name."""
        state = {DM: {"members": [member(ME, "Sam"), member(JANE, "Sam")]}}
        listed, _ = self.list_rooms(state)
        self.assertEqual(listed[DM]["name"], f"Sam ({JANE})")

    def test_display_name_shared_by_two_others_is_qualified(self):
        bob = "@bob:example.org"
        state = {
            GROUP: {"members": [member(ME), member(JANE, "Sam"), member(bob, "Sam")]}
        }
        listed, _ = self.list_rooms(state)
        self.assertEqual(listed[GROUP]["name"], f"Sam ({bob}) and Sam ({JANE})")

    def test_unreadable_members_keep_the_room_id(self):
        listed, _ = self.list_rooms({DM: {"members": None}})
        self.assertEqual(listed[DM]["name"], DM)
        self.assertNotIn("members", listed[DM])

    def test_named_room_is_unchanged_and_costs_no_member_request(self):
        listed, server = self.list_rooms({OPS: STATE[OPS]})
        self.assertEqual(
            listed[OPS], {"room_id": OPS, "name": "Ops", "alias": "#ops:example.org"}
        )
        self.assertFalse([c for c in server.calls if "/members" in c])

    def test_alias_only_room_is_named_by_alias(self):
        listed, _ = self.list_rooms({OPS: {"alias": "#ops:example.org"}})
        self.assertEqual(listed[OPS]["name"], "#ops:example.org")
        self.assertNotIn("members", listed[OPS])

    def test_group_name_wording_matches_nio(self):
        self.assertEqual(rooms.group_name([]), "Empty Room")
        self.assertEqual(rooms.group_name(["Jane"]), "Jane")
        self.assertEqual(rooms.group_name(["Max", "Jane"]), "Jane and Max")
        self.assertEqual(rooms.group_name(["c", "b", "a"]), "a, b and c")
        six = ["a", "b", "c", "d", "e", "f"]
        self.assertEqual(rooms.group_name(six), "a, b, c, d, e and 1 other")
        self.assertEqual(rooms.group_name([*six, "g"]), "a, b, c, d, e and 2 others")


class FindRoomByNameTests(unittest.TestCase):
    def find(self, term, state=STATE):
        server = fake_rooms_server(state)
        with unittest.mock.patch.object(rooms, "matrix_request", server):
            return rooms.find_room_by_name(CONFIG, term)

    def test_lookup_by_display_name_finds_the_direct_chat(self):
        """An unnamed group with Jane in it does not make this ambiguous."""
        room_id, _ = self.find("Jane Doe")
        self.assertEqual(room_id, DM)

    def test_lookup_by_user_id_finds_the_direct_chat_when_unique(self):
        room_id, _ = self.find(JANE, {DM: STATE[DM], OPS: STATE[OPS]})
        self.assertEqual(room_id, DM)

    def test_user_id_shared_by_two_unnamed_rooms_is_not_guessed(self):
        room_id, matches = self.find(JANE)
        self.assertIsNone(room_id)
        self.assertEqual({m["room_id"] for m in matches}, {DM, GROUP})

    def test_search_on_surname_finds_the_direct_chat(self):
        room_id, _ = self.find("doe", {DM: STATE[DM], OPS: STATE[OPS]})
        self.assertEqual(room_id, DM)

    def test_named_room_still_found_by_alias_name(self):
        room_id, _ = self.find("ops")
        self.assertEqual(room_id, OPS)

    def test_named_rooms_keep_the_disambiguation_rule(self):
        """An alias-less exact match next to a named room containing the term."""
        state = {"!a:x": {"name": "Ops"}, "!b:x": {"name": "Ops Team"}}
        room_id, matches = self.find("ops", state)
        self.assertIsNone(room_id)
        self.assertEqual(len(matches), 2)

    def test_named_room_does_not_match_on_members(self):
        state = {OPS: {"name": "Ops", "members": [member(JANE, "Jane Doe")]}}
        room_id, matches = self.find("jane", state)
        self.assertIsNone(room_id)
        self.assertEqual(matches, [])


class FakeNioRoom:
    def __init__(self, users, name=None, canonical_alias=None, display_name=None):
        self.users = {u: object() for u in users}
        self.own_user_id = ME
        self.name = name
        self.canonical_alias = canonical_alias
        self.display_name = display_name or name or canonical_alias


NIO_ROOMS = {
    DM: FakeNioRoom([ME, JANE], display_name="Jane Doe"),
    GROUP: FakeNioRoom([ME, JANE, "@max:example.org"], display_name="Jane Doe and Max"),
    OPS: FakeNioRoom([ME, JANE], name="Ops", canonical_alias="#ops:example.org"),
}


class FindRoomInNioClientTests(unittest.TestCase):
    def find(self, term, client_rooms=None):
        return rooms.find_room_in_nio_client(client_rooms or NIO_ROOMS, term)

    def test_display_name_finds_the_direct_chat(self):
        self.assertEqual(self.find("Jane Doe"), DM)

    def test_user_id_finds_the_direct_chat_when_unique(self):
        only_dm = {DM: NIO_ROOMS[DM], OPS: NIO_ROOMS[OPS]}
        self.assertEqual(self.find(JANE, only_dm), DM)

    def test_user_id_shared_by_two_unnamed_rooms_is_not_guessed(self):
        self.assertIsNone(self.find(JANE))

    def test_partial_user_id_finds_the_direct_chat(self):
        """`@jane:` is in the user ID only, never in the display name."""
        only_dm = {DM: NIO_ROOMS[DM], OPS: NIO_ROOMS[OPS]}
        self.assertEqual(self.find("@jane:", only_dm), DM)

    def test_own_user_id_matches_nothing(self):
        only_dm = {DM: NIO_ROOMS[DM]}
        self.assertIsNone(self.find(ME, only_dm))

    def test_named_room_does_not_match_on_members(self):
        self.assertIsNone(self.find("@jane", {OPS: NIO_ROOMS[OPS]}))


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

    def test_resolve_room_cli_takes_a_permalink(self):
        link = "https://matrix.to/#/!abc:example.org?via=example.org"

        def no_request(*args, **kwargs):
            raise AssertionError("a room ID needs no request")

        with unittest.mock.patch.object(rooms, "matrix_request", no_request):
            self.assertEqual(rooms.resolve_room_cli(CONFIG, link), "!abc:example.org")


if __name__ == "__main__":
    unittest.main()
