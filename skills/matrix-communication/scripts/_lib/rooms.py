# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Room operations for Matrix scripts.

All functions use ONLY stdlib.
"""

import json
import sys
import urllib.parse
from collections import Counter

from _lib.formatting import MATRIX_TO
from _lib.http import matrix_request, path_segment

# nio's MatrixRoom.group_name() lists at most this many members by name.
GROUP_NAME_HEROES = 5


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


def group_name(names: list[str]) -> str:
    """Name a room without m.room.name or alias after its members.

    Same wording as matrix-nio's MatrixRoom.group_name(), so the HTTP path
    and the nio path give a direct chat the same name: the other person's
    display name, "A and B", "A, B and 3 others", or "Empty Room".
    """
    names = sorted(names, key=str.lower)
    shown = names[:GROUP_NAME_HEROES]
    others = len(names) - len(shown)
    if not shown:
        return "Empty Room"
    if others:
        return f"{', '.join(shown)} and {others} other{'' if others == 1 else 's'}"
    if len(shown) == 1:
        return shown[0]
    return f"{', '.join(shown[:-1])} and {shown[-1]}"


def get_room_members(config: dict, room_id: str) -> dict | None:
    """Return the joined and invited members of a room except this account.

    One request. Invited members count because a direct chat whose partner
    has not accepted yet is still the chat with that person - nio's
    room.users holds them too. A display name that two members share, this
    account included, becomes "Name (@user:server)", as nio's user_name()
    and the spec's room-name rules have it.

    Returns:
        Dict of user ID -> display name (the user ID when none is set),
        or None when the server refused the request
    """
    result = matrix_request(
        config,
        "GET",
        f"/rooms/{path_segment(room_id)}/members?not_membership=leave",
    )
    if "error" in result:
        return None
    display_names = {}
    for event in result.get("chunk", []):
        user_id = event.get("state_key")
        content = event.get("content", {})
        if not user_id or content.get("membership") not in ("join", "invite"):
            continue
        display_names[user_id] = content.get("displayname")
    taken = Counter(name or user_id for user_id, name in display_names.items())
    members = {}
    for user_id, name in display_names.items():
        if user_id == config.get("user_id"):
            continue
        if name and taken[name] > 1:
            name = f"{name} ({user_id})"
        members[user_id] = name or user_id
    return members


def room_matches(room: dict, search_lower: str, exact: bool = False) -> bool:
    """Whether a room dict from list_joined_rooms() matches a search term.

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


def resolve_room_alias(config: dict, alias: str) -> str:
    """Resolve a room alias to room ID.

    Args:
        config: Matrix config with homeserver and access_token
        alias: Room alias (e.g., #room:server)

    Returns:
        Room ID (e.g., !abc123:server)

    Raises:
        ValueError if alias cannot be resolved
    """
    encoded_alias = urllib.parse.quote(alias, safe="")
    result = matrix_request(config, "GET", f"/directory/room/{encoded_alias}")
    if "room_id" in result:
        return result["room_id"]
    raise ValueError(
        f"Could not resolve room alias: {result.get('error', 'Unknown error')}"
    )


def get_room_info(config: dict, room_id: str) -> dict:
    """Get the display name and canonical alias of a room.

    Args:
        config: Matrix config with homeserver and access_token
        room_id: Room ID to query

    Returns:
        Dict with 'name' and 'alias' keys (values may be None)
    """
    info = {"name": None, "alias": None}

    result = matrix_request(
        config, "GET", f"/rooms/{path_segment(room_id)}/state/m.room.name"
    )
    if "name" in result:
        info["name"] = result["name"]

    result = matrix_request(
        config, "GET", f"/rooms/{path_segment(room_id)}/state/m.room.canonical_alias"
    )
    if "alias" in result:
        info["alias"] = result["alias"]

    return info


def list_joined_rooms(config: dict) -> list:
    """List all joined rooms with names and aliases.

    A room with neither m.room.name nor an alias - a direct chat, usually -
    is named after its members the way Element and nio name it, which costs
    one more request for each such room.

    Args:
        config: Matrix config with homeserver and access_token

    Returns:
        List of dicts with room_id, name, and alias keys; a room named after
        its members also has `members`, the user IDs it was named from
    """
    result = matrix_request(config, "GET", "/joined_rooms")
    if "error" in result:
        return []

    rooms = []
    for room_id in result.get("joined_rooms", []):
        info = get_room_info(config, room_id)
        room = {
            "room_id": room_id,
            "name": info["name"] or info["alias"],
            "alias": info["alias"],
        }
        if not room["name"]:
            members = get_room_members(config, room_id)
            if members is None:
                # Members unreadable: keep the bare ID rather than call a
                # room with people in it "Empty Room".
                room["name"] = room_id
            else:
                room["name"] = group_name(list(members.values()))
                room["members"] = sorted(members)
        rooms.append(room)

    return rooms


def find_room_by_name(config: dict, search_term: str) -> tuple[str | None, list]:
    """Find a room by name or alias (case-insensitive).

    Match priority:
    1. Exact alias match (#room:server)
    2. Exact alias name match (without server part, e.g. "agent-work")
    3. Exact room name match (rooms with aliases preferred)
    4. Single partial match on name or alias

    When an exact name match has no alias but other rooms also have names
    containing the search term, all candidates are returned for disambiguation.

    Args:
        config: Matrix config with homeserver and access_token
        search_term: Search term to match against room names/aliases

    Returns:
        (room_id, matches) where:
        - room_id is the matched room ID (or None if no/ambiguous match)
        - matches is list of matching rooms (for error reporting)
    """
    rooms = list_joined_rooms(config)
    search_lower = search_term.lower()

    # Try exact alias match (most specific)
    for room in rooms:
        if room.get("alias") and room["alias"].lower() == search_lower:
            return room["room_id"], [room]

    # Try exact alias name match (without server part)
    for room in rooms:
        if room.get("alias"):
            alias_name = room["alias"].split(":")[0].lstrip("#")
            if alias_name.lower() == search_lower:
                return room["room_id"], [room]

    # Try exact name match (for a room named after its members, also a
    # member's user ID)
    name_matches = [r for r in rooms if room_matches(r, search_lower, exact=True)]
    if len(name_matches) == 1:
        room = name_matches[0]
        if room.get("alias"):
            # Room has an alias — well-identified, return directly
            return room["room_id"], name_matches
        # Room has no alias — check if other rooms have names containing
        # the search term, which suggests the user may want a different room.
        # Only names someone gave a room count here: a name made up from
        # members ("Jane Doe and Max") is not a competing room name, and
        # before such names existed these rooms never competed either.
        alternatives = [
            r
            for r in rooms
            if r not in name_matches
            and "members" not in r
            and search_lower in r["name"].lower()
        ]
        if alternatives:
            return None, name_matches + alternatives
        return room["room_id"], name_matches
    if len(name_matches) > 1:
        return None, name_matches

    # Try partial match
    matches = [r for r in rooms if room_matches(r, search_lower)]

    if len(matches) == 1:
        return matches[0]["room_id"], matches

    return None, matches


def find_room_in_nio_client(client_rooms: dict, search_term: str) -> str | None:
    """Find a room by name in a matrix-nio client.rooms dict (post-sync).

    This avoids the N+1 HTTP calls of find_room_by_name() by using
    room data already loaded by client.sync().

    Args:
        client_rooms: dict from AsyncClient.rooms (room_id -> MatrixRoom)
        search_term: Room name, alias, or ID to match

    Returns:
        room_id if found, None otherwise
    """
    search_lower = search_term.lower()

    def member_ids(room) -> list[str]:
        # Like list_joined_rooms(): only a room named after its members
        # matches on their user IDs; named rooms match as before.
        if room.name or room.canonical_alias:
            return []
        own = getattr(room, "own_user_id", None)
        return [u.lower() for u in room.users if u != own]

    # Exact alias match
    for room_id, room in client_rooms.items():
        if room.canonical_alias and room.canonical_alias.lower() == search_lower:
            return room_id

    # Alias name match (without server part)
    for room_id, room in client_rooms.items():
        if room.canonical_alias:
            alias_name = room.canonical_alias.split(":")[0].lstrip("#")
            if alias_name.lower() == search_lower:
                return room_id

    # Exact display name match (for a room named after its members, also a
    # member's user ID)
    exact_matches = [
        room_id
        for room_id, room in client_rooms.items()
        if (room.display_name and room.display_name.lower() == search_lower)
        or search_lower in member_ids(room)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None  # Ambiguous exact match

    # Partial name match
    partial_matches = [
        room_id
        for room_id, room in client_rooms.items()
        if search_lower in (room.display_name or "").lower()
        or search_lower in (room.canonical_alias or "").lower()
        or any(search_lower in u for u in member_ids(room))
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]

    return None


def find_direct_room(config: dict, user_id: str) -> str:
    """Find the direct-message room shared with `user_id`.

    A name search finds a direct chat by the other person's name, but not
    when the chat has a name of its own or when the person shares unnamed
    rooms with this account besides it. The account data `m.direct` maps
    each user to the rooms marked as direct with them; it still lists rooms
    either side has left. A room counts only when this account is joined to
    it and `user_id` is joined or invited. Nothing is created: no usable
    room is an error.

    Args:
        config: Matrix config with homeserver, user_id and access_token
        user_id: Full Matrix ID of the other person (@user:server)

    Returns:
        Room ID of the single usable direct room

    Raises:
        ValueError if there is no usable direct room, or more than one
    """
    direct = matrix_request(
        config,
        "GET",
        f"/user/{path_segment(config['user_id'])}/account_data/m.direct",
    )
    if "error" in direct and direct.get("errcode") != "M_NOT_FOUND":
        raise ValueError(f"Could not read m.direct: {direct['error']}")
    listed = direct.get(user_id, [])
    if not listed:
        raise ValueError(f"No direct chat with {user_id} in m.direct")

    joined_rooms = matrix_request(config, "GET", "/joined_rooms")
    if "error" in joined_rooms:
        raise ValueError(f"Could not list joined rooms: {joined_rooms['error']}")
    joined = set(joined_rooms.get("joined_rooms", []))

    usable = []
    for room_id in listed:
        if room_id not in joined:
            continue
        member = matrix_request(
            config,
            "GET",
            f"/rooms/{path_segment(room_id)}/state/m.room.member/"
            f"{path_segment(user_id)}",
        )
        if member.get("membership") in ("join", "invite"):
            usable.append(room_id)

    if len(usable) == 1:
        return usable[0]
    if not usable:
        raise ValueError(
            f"No usable direct chat with {user_id}: m.direct lists "
            f"{', '.join(listed)}, but you or they have left each of them"
        )
    raise ValueError(
        f"Several direct chats with {user_id}: {', '.join(usable)}. "
        "Pass the room ID instead of --to"
    )


def resolve_room_cli(
    config: dict, room_input: str, json_out: bool = False, debug: bool = False
) -> str:
    """Resolve a ROOM CLI argument (ID, alias, name, or matrix.to link).

    Shared by scripts that take a ROOM positional argument, so each script
    doesn't reimplement the same ID/alias/name resolution order and error
    formatting. Prints a JSON or human-readable error and exits 1 if the
    room cannot be resolved — callers can assume a valid room ID is
    returned or the process has already ended.
    """
    room_input = normalize_room_input(room_input)
    if room_input.startswith("!"):
        if debug:
            print(f"Using room ID directly: {room_input}", file=sys.stderr)
        return room_input

    if room_input.startswith("#"):
        try:
            room_id = resolve_room_alias(config, room_input)
            if debug:
                print(f"Resolved alias {room_input} -> {room_id}", file=sys.stderr)
            return room_id
        except ValueError as e:
            if json_out:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    found_id, matches = find_room_by_name(config, room_input)
    if found_id:
        if debug:
            print(f"Found room: {found_id}", file=sys.stderr)
        return found_id

    error_msg = f"Could not find room '{room_input}'"
    if matches:
        error_msg += ". Multiple matches found:\n"
        for m in matches:
            alias_str = f" ({m['alias']})" if m.get("alias") else ""
            error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
    else:
        error_msg += ". Use 'matrix-rooms.py' to list available rooms."
    if json_out:
        print(json.dumps({"error": error_msg}))
    else:
        print(f"Error: {error_msg}", file=sys.stderr)
    sys.exit(1)
