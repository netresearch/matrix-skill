#!/usr/bin/env python3
"""List joined Matrix rooms.

Usage:
    matrix-rooms.py [--json] [--search TERM]
    matrix-rooms.py --lookup NAME
    matrix-rooms.py --help

Options:
    --json            Output as JSON
    --search TERM     Filter rooms by name or alias
    --lookup NAME     Find room by name and output room ID (for scripts)
    --help            Show this help

Examples:
    # List all rooms with names, aliases, and IDs
    matrix-rooms.py

    # Search for rooms containing "agent"
    matrix-rooms.py --search agent

    # Get room ID by name (for use in other commands)
    matrix-rooms.py --lookup "agent-work"

    # Use in pipeline
    matrix-send.py "$(matrix-rooms.py --lookup agent-work)" "Hello!"
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def load_config() -> dict:
    """Load Matrix config from ~/.config/matrix/config.json"""
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def matrix_request(config: dict, method: str, endpoint: str) -> dict:
    """Make a Matrix API request."""
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            return {"error": error_json.get("error", error_body)}
        except:
            return {"error": error_body}


def get_room_info(config: dict, room_id: str) -> dict:
    """Get the display name and canonical alias of a room."""
    info = {"name": None, "alias": None}

    # Get room name
    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.name")
    if "name" in result:
        info["name"] = result["name"]

    # Get canonical alias
    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.canonical_alias")
    if "alias" in result:
        info["alias"] = result["alias"]

    return info


def list_rooms(config: dict) -> list:
    """List all joined rooms with names and aliases."""
    result = matrix_request(config, "GET", "/joined_rooms")
    if "error" in result:
        return []

    rooms = []
    for room_id in result.get("joined_rooms", []):
        info = get_room_info(config, room_id)
        # Display name priority: name > alias > room_id
        display_name = info["name"] or info["alias"] or room_id
        rooms.append({
            "room_id": room_id,
            "name": display_name,
            "alias": info["alias"]  # Keep alias separate for lookup
        })

    return sorted(rooms, key=lambda r: r["name"].lower())


def find_room_by_name(config: dict, search_term: str) -> dict | None:
    """Find a room by name or alias (case-insensitive partial match).

    Returns the best matching room or None if not found.
    Exact matches are preferred over partial matches.
    """
    rooms = list_rooms(config)
    search_lower = search_term.lower()

    # Try exact match first (name or alias)
    for room in rooms:
        if room["name"].lower() == search_lower:
            return room
        if room.get("alias") and room["alias"].lower() == search_lower:
            return room
        # Also match alias without server part (e.g., "agent-work" matches "#agent-work:server")
        if room.get("alias"):
            alias_name = room["alias"].split(":")[0].lstrip("#")
            if alias_name.lower() == search_lower:
                return room

    # Try partial match
    matches = []
    for room in rooms:
        if search_lower in room["name"].lower():
            matches.append(room)
        elif room.get("alias") and search_lower in room["alias"].lower():
            if room not in matches:
                matches.append(room)

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        # Return None to indicate ambiguous match (caller should list options)
        return None

    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="List joined Matrix rooms")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--search", "-s", help="Filter rooms by name")
    parser.add_argument("--lookup", "-l", metavar="NAME",
                        help="Find room by name and output room ID (for scripts)")

    args = parser.parse_args()

    config = load_config()

    # Lookup mode: find a specific room and print its ID
    if args.lookup:
        room = find_room_by_name(config, args.lookup)
        if room:
            if args.json:
                print(json.dumps(room, indent=2))
            else:
                print(room["room_id"])
            return
        else:
            # Check if it's an ambiguous match
            rooms = list_rooms(config)
            search_lower = args.lookup.lower()
            matches = [r for r in rooms if search_lower in r["name"].lower() or
                      (r.get("alias") and search_lower in r["alias"].lower())]
            if matches:
                print(f"Error: Ambiguous match for '{args.lookup}'. Found {len(matches)} rooms:", file=sys.stderr)
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    print(f"  - {m['name']}{alias_str}: {m['room_id']}", file=sys.stderr)
            else:
                print(f"Error: No room found matching '{args.lookup}'", file=sys.stderr)
            sys.exit(1)

    rooms = list_rooms(config)

    if args.search:
        search_lower = args.search.lower()
        rooms = [r for r in rooms if search_lower in r["name"].lower() or
                (r.get("alias") and search_lower in r["alias"].lower())]

    if args.json:
        print(json.dumps(rooms, indent=2))
    else:
        if not rooms:
            print("No rooms found")
            return

        print(f"{'Room Name':<40} {'Alias':<35} {'Room ID'}")
        print("-" * 120)
        for room in rooms:
            name = room["name"][:38] if len(room["name"]) > 38 else room["name"]
            alias = room.get("alias") or ""
            alias = alias[:33] if len(alias) > 33 else alias
            print(f"{name:<40} {alias:<35} {room['room_id']}")


if __name__ == "__main__":
    main()
