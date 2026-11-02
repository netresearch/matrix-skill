#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List joined Matrix rooms.

Usage:
    matrix-rooms.py [--json] [--search TERM]
    matrix-rooms.py --lookup NAME
    matrix-rooms.py --help

Options:
    --json            Output as JSON
    --search TERM     Filter rooms by name or alias; a room without a name
                      (a direct chat) is named after its members and also
                      matches on their user IDs
    --lookup NAME     Find room by name and output room ID (for scripts)
    --help            Show this help

Examples:
    # List all rooms with names, aliases, and IDs
    matrix-rooms.py

    # Search for rooms containing "agent"
    matrix-rooms.py --search agent

    # Find the direct chat with Jane Doe (by display name or user ID)
    matrix-rooms.py --lookup "Jane Doe"
    matrix-rooms.py --search @jane:example.org

    # Get room ID by name (for use in other commands)
    matrix-rooms.py --lookup "agent-work"

    # Use in pipeline
    matrix-send.py "$(matrix-rooms.py --lookup agent-work)" "Hello!"
"""

import json
import os
import sys

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import find_room_by_name, list_joined_rooms, load_config, room_matches

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="List joined Matrix rooms")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--search", "-s", help="Filter rooms by name, alias or member user ID"
    )
    parser.add_argument(
        "--lookup",
        "-l",
        metavar="NAME",
        help="Find room by name and output room ID (for scripts)",
    )

    args = parser.parse_args()

    config = load_config()

    # Lookup mode: find a specific room and print its ID
    if args.lookup:
        room_id, matches = find_room_by_name(config, args.lookup)
        if room_id:
            if args.json:
                # Find the full room info from matches
                room_info = matches[0] if matches else {"room_id": room_id}
                print(json.dumps(room_info, indent=2))
            else:
                print(room_id)
            return
        else:
            # Check if it's an ambiguous match
            if matches:
                print(
                    f"Error: Ambiguous match for '{args.lookup}'. Found {len(matches)} rooms:",
                    file=sys.stderr,
                )
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    print(
                        f"  - {m['name']}{alias_str}: {m['room_id']}", file=sys.stderr
                    )
            else:
                print(f"Error: No room found matching '{args.lookup}'", file=sys.stderr)
            sys.exit(1)

    rooms = list_joined_rooms(config)
    rooms = sorted(rooms, key=lambda r: r["name"].lower())

    if args.search:
        rooms = [r for r in rooms if room_matches(r, args.search.lower())]

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
