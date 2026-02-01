"""Room operations for Matrix scripts.

All functions use ONLY stdlib.
"""

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
    encoded_alias = urllib.parse.quote(alias, safe='')
    result = matrix_request(config, "GET", f"/directory/room/{encoded_alias}")
    if "room_id" in result:
        return result["room_id"]
    raise ValueError(f"Could not resolve room alias: {result.get('error', 'Unknown error')}")


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

    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.canonical_alias")
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
        rooms.append({
            "room_id": room_id,
            "name": display_name,
            "alias": info["alias"]
        })

    return rooms


def find_room_by_name(config: dict, search_term: str) -> tuple[str | None, list]:
    """Find a room by name or alias (case-insensitive).

    Supports:
    - Exact match on room name
    - Exact match on full alias (#room:server)
    - Exact match on alias name without server (e.g., "agent-work" matches "#agent-work:server")
    - Partial match on name or alias

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

    # Try exact match first
    for room in rooms:
        if room["name"].lower() == search_lower:
            return room["room_id"], [room]
        if room.get("alias") and room["alias"].lower() == search_lower:
            return room["room_id"], [room]
        # Match alias without server part (e.g., "agent-work" matches "#agent-work:server")
        if room.get("alias"):
            alias_name = room["alias"].split(":")[0].lstrip("#")
            if alias_name.lower() == search_lower:
                return room["room_id"], [room]

    # Try partial match
    matches = []
    for room in rooms:
        if search_lower in room["name"].lower():
            matches.append(room)
        elif room.get("alias") and search_lower in room["alias"].lower():
            if room not in matches:
                matches.append(room)

    if len(matches) == 1:
        return matches[0]["room_id"], matches

    return None, matches
