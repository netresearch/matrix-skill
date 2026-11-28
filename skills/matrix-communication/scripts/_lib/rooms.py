# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Room arguments for Matrix scripts.

All functions use ONLY stdlib. The joined rooms come from matrix-e2ee-cli
(``rooms --json``, see room_lookup.py); this module reads matrix.to links and
matches a search term against one room of that list.
"""

import urllib.parse

from _lib.formatting import MATRIX_TO


def normalize_room_input(room_input: str) -> str:
    """Turn a matrix.to permalink into the room ID or alias it points at.

    Element's "Copy link" gives `https://matrix.to/#/!room:server?via=...`,
    `https://matrix.to/#/#alias:server`, or for a message
    `https://matrix.to/#/!room:server/$event?via=...`, sometimes
    percent-encoded. The room part is returned decoded; the event part and
    the query are dropped. Anything that is not such a link is returned
    unchanged.
    """
    if not room_input.startswith(MATRIX_TO):
        return room_input
    target = room_input[len(MATRIX_TO) :].split("?", 1)[0].split("/", 1)[0]
    return urllib.parse.unquote(target)


def room_matches(room: dict, search_lower: str, exact: bool = False) -> bool:
    """Whether a room dict of `matrix-e2ee-cli rooms --json` matches a search term.

    Matches the room name, the alias, and - for a room named after its
    members - the members' user IDs, so `@jane:server` finds the direct
    chat with Jane. Named rooms carry no member list and match as before.
    """
    members = [m.lower() for m in room.get("members", [])]
    if exact:
        return room["name"].lower() == search_lower or search_lower in members
    return (
        search_lower in room["name"].lower()
        or search_lower in (room.get("alias") or "").lower()
        or any(search_lower in m for m in members)
    )
