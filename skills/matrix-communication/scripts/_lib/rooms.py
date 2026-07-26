"""Room operations for Matrix scripts.

All functions use ONLY stdlib.
"""

import json
import sys
import urllib.parse

from _lib.http import matrix_request


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

    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.name")
    if "name" in result:
        info["name"] = result["name"]

    result = matrix_request(
        config, "GET", f"/rooms/{room_id}/state/m.room.canonical_alias"
    )
    if "alias" in result:
        info["alias"] = result["alias"]

    return info


def list_joined_rooms(config: dict) -> list:
    """List all joined rooms with names and aliases.

    Args:
        config: Matrix config with homeserver and access_token

    Returns:
        List of dicts with room_id, name, and alias keys
    """
    result = matrix_request(config, "GET", "/joined_rooms")
    if "error" in result:
        return []

    rooms = []
    for room_id in result.get("joined_rooms", []):
        info = get_room_info(config, room_id)
        display_name = info["name"] or info["alias"] or room_id
        rooms.append({"room_id": room_id, "name": display_name, "alias": info["alias"]})

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

    # Try exact name match
    name_matches = [r for r in rooms if r["name"].lower() == search_lower]
    if len(name_matches) == 1:
        room = name_matches[0]
        if room.get("alias"):
            # Room has an alias — well-identified, return directly
            return room["room_id"], name_matches
        # Room has no alias — check if other rooms have names containing
        # the search term, which suggests the user may want a different room
        alternatives = [
            r
            for r in rooms
            if r not in name_matches and search_lower in r["name"].lower()
        ]
        if alternatives:
            return None, name_matches + alternatives
        return room["room_id"], name_matches
    if len(name_matches) > 1:
        return None, name_matches

    # Try partial match
    matches = []
    for room in rooms:
        if search_lower in room["name"].lower():
            matches.append(room)
        elif room.get("alias") and search_lower in room["alias"].lower():  # noqa: SIM102  # kept nested for readability of partial-match dedup
            if room not in matches:
                matches.append(room)

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

    # Exact display name match
    exact_matches = [
        room_id
        for room_id, room in client_rooms.items()
        if room.display_name and room.display_name.lower() == search_lower
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
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]

    return None


def resolve_room_cli(
    config: dict, room_input: str, json_out: bool = False, debug: bool = False
) -> str:
    """Resolve a ROOM CLI argument (ID, alias, or name) to a room ID.

    Shared by scripts that take a ROOM positional argument, so each script
    doesn't reimplement the same ID/alias/name resolution order and error
    formatting. Prints a JSON or human-readable error and exits 1 if the
    room cannot be resolved — callers can assume a valid room ID is
    returned or the process has already ended.
    """
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
