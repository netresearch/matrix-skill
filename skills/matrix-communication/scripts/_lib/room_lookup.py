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
from _lib.rooms import find_room_by_name, list_joined_rooms


class RoomLookupError(Exception):
    """The shorthand matched no room, several rooms, or could not be looked up."""


def is_shorthand(room: str) -> bool:
    """Not a room ID and not an alias with its server part."""
    return not room.startswith("!") and not (room.startswith("#") and ":" in room)


def resolve(room: str, env, lister=list_joined_rooms) -> str:
    """The room ID the old scripts chose for ROOM; ROOM itself when it is exact.

    Without a session there is nothing to look up with, and the CLI, which
    needs the session too, reports that itself.
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
    room_id, matches = find_room_by_name(config, term, rooms=rooms)
    if room_id:
        return room_id
    if matches:
        listed = ", ".join(
            f"{m.get('name')} ({m.get('alias') or m['room_id']})" for m in matches
        )
        raise RoomLookupError(
            f"{room!r} matches several rooms: {listed}; pass the room ID or full alias"
        )
    raise RoomLookupError(
        f"no joined room matches {room!r}; matrix-rooms.py lists them"
    )
