#!/usr/bin/env python3
"""List joined Matrix rooms.

Usage:
    matrix-rooms.py [--json] [--search TERM]
    matrix-rooms.py --help

Options:
    --json          Output as JSON
    --search TERM   Filter rooms by name
    --help          Show this help
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


def get_room_name(config: dict, room_id: str) -> str:
    """Get the display name of a room."""
    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.name")
    if "name" in result:
        return result["name"]

    # Try canonical alias
    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.canonical_alias")
    if "alias" in result:
        return result["alias"]

    return room_id


def list_rooms(config: dict) -> list:
    """List all joined rooms with names."""
    result = matrix_request(config, "GET", "/joined_rooms")
    if "error" in result:
        return []

    rooms = []
    for room_id in result.get("joined_rooms", []):
        name = get_room_name(config, room_id)
        rooms.append({
            "room_id": room_id,
            "name": name
        })

    return sorted(rooms, key=lambda r: r["name"].lower())


def main():
    import argparse

    parser = argparse.ArgumentParser(description="List joined Matrix rooms")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--search", "-s", help="Filter rooms by name")

    args = parser.parse_args()

    config = load_config()
    rooms = list_rooms(config)

    if args.search:
        search_lower = args.search.lower()
        rooms = [r for r in rooms if search_lower in r["name"].lower()]

    if args.json:
        print(json.dumps(rooms, indent=2))
    else:
        if not rooms:
            print("No rooms found")
            return

        print(f"{'Room Name':<50} {'Room ID'}")
        print("-" * 100)
        for room in rooms:
            name = room["name"][:48] if len(room["name"]) > 48 else room["name"]
            print(f"{name:<50} {room['room_id']}")


if __name__ == "__main__":
    main()
