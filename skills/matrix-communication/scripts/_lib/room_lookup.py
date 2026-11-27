# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Resolve a room shorthand the way the scripts did before matrix-e2ee-cli.

Stdlib only. matrix-e2ee-cli reads ROOM as a room ID (``!…``), a full alias
(``#name:server``) or, for anything else, an exact display name. The scripts
of version 4 resolved a shorthand differently: an alias without its server
part (``ops`` or ``#ops`` for ``#ops:example.org``) came before a display
name, and a single partial match counted too. Passed on unchanged, ``ops``
can therefore reach a different room than before, and both succeed.

So a shorthand is resolved here, with the old precedence (``find_room_by_name``
in rooms.py), to a room ID, and only the ID reaches the CLI. Room IDs and full
aliases pass unchanged, without a request. The lookup reads the joined rooms
over HTTP with the skill's own device token from matrix-e2ee-cli's
session.json: two requests per joined room (name and alias), one more for a
room without either, as before for matrix-react.py and matrix-redact.py. No match, several matches, or rooms that cannot be listed
stop the command: it never falls back to the CLI's own, different choice.
"""

import json

from _lib import cutover
from _lib.rooms import find_room_by_name, list_joined_rooms, room_matches


class RoomLookupError(Exception):
    """The shorthand matched no room, several rooms, or could not be looked up."""


def is_shorthand(room: str) -> bool:
    """Not a room ID and not an alias with its server part."""
    return not room.startswith("!") and not (room.startswith("#") and ":" in room)


def _alias_localpart(room: dict) -> str:
    return (room.get("alias") or "").split(":")[0].lstrip("#").lower()


def _listed(rooms) -> str:
    return ", ".join(
        f"{r.get('name')} ({r.get('alias') or r['room_id']})" for r in rooms
    )


def resolve(room: str, env, lister=list_joined_rooms, write=False) -> str:
    """The room ID the old scripts chose for ROOM; ROOM itself when it is exact.

    Without a session there is nothing to look up with, and the CLI, which
    needs the session too, reports that itself. With WRITE (send, edit,
    react, redact) only an exact alias or an exact name counts: a room
    name is chosen by whoever named the room, and a partial match would
    let such a name decide where a message goes.
    """
    if not is_shorthand(room):
        return room
    # matrix-send-e2ee.py and friends looked "#ops" up as the name "ops".
    term = room.removeprefix("#")
    try:
        session = json.loads(cutover.cli_session_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError, cutover.CutoverError):
        return room
    config = {
        "homeserver": session.get("homeserver"),
        "access_token": session.get("access_token"),
        "user_id": session.get("user_id"),
    }
    if not config["homeserver"] or not config["access_token"]:
        # The CLI would pick by display name alone: refuse rather than guess.
        raise RoomLookupError(
            f"cannot look {room!r} up: the matrix-e2ee-cli session has no homeserver "
            "or access token; pass the room ID (!…) or full alias (#name:server)"
        )
    rooms = lister(config)
    if not rooms:
        raise RoomLookupError(
            f"cannot list the joined rooms to find {room!r}; pass its room ID (!…) "
            "or full alias (#name:server)"
        )
    lowered = term.lower()
    by_alias = [r for r in rooms if r.get("alias") and _alias_localpart(r) == lowered]
    if len(by_alias) > 1:
        # find_room_by_name would take the first: two servers, one localpart.
        raise RoomLookupError(
            f"{room!r} matches several rooms: {_listed(by_alias)}; pass the room ID "
            "or full alias"
        )
    room_id, matches = find_room_by_name(config, term, rooms=rooms)
    if room_id and write:
        chosen = [r for r in rooms if r["room_id"] == room_id]
        exact = any(
            _alias_localpart(r) == lowered or room_matches(r, lowered, exact=True)
            for r in chosen
        )
        if not exact:
            raise RoomLookupError(
                f"{room!r} is only part of the name of {_listed(chosen)}; a command "
                "that writes needs the exact name, the room ID or the full alias"
            )
    if room_id:
        return room_id
    if matches:
        raise RoomLookupError(
            f"{room!r} matches several rooms: {_listed(matches)}; pass the room ID or "
            "full alias"
        )
    raise RoomLookupError(
        f"no joined room matches {room!r}; matrix-rooms.py lists them"
    )
