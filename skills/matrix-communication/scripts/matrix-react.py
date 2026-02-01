#!/usr/bin/env python3
"""React to a Matrix message with an emoji.

Usage:
    matrix-react.py ROOM EVENT_ID EMOJI
    matrix-react.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name
    EVENT_ID    Event ID of message to react to (e.g., $abc123...)
    EMOJI       Emoji reaction (e.g., checkmark, thumbsup, party)

Options:
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help

Examples:
    # Add checkmark reaction
    matrix-react.py "#ops:matrix.org" "$eventid" "checkmark"

    # Thumbs up
    matrix-react.py "#dev:matrix.org" "$eventid" "thumbsup"
"""

import json
import sys
import os
import time

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    matrix_request,
    resolve_room_alias,
    find_room_by_name,
    clean_message,
)


def send_reaction(config: dict, room_id: str, event_id: str, emoji: str) -> dict:
    """Send a reaction to a message.

    Reactions use the m.reaction event type with m.annotation relation.
    """
    txn_id = str(int(time.time() * 1000))

    content = {
        "m.relates_to": {
            "rel_type": "m.annotation",
            "event_id": event_id,
            "key": emoji
        }
    }

    return matrix_request(config, "PUT", f"/rooms/{room_id}/send/m.reaction/{txn_id}", content)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="React to a Matrix message with an emoji")
    parser.add_argument("room", help="Room alias (#room:server), room ID (!id:server), or room name")
    parser.add_argument("event_id", help="Event ID of message to react to")
    parser.add_argument("emoji", help="Emoji reaction (e.g., checkmark, thumbsup, party)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Clean and resolve room
    room_input = clean_message(args.room)
    room_id = room_input

    if room_input.startswith("!"):
        # Direct room ID
        room_id = room_input
        if args.debug:
            print(f"Using room ID directly: {room_id}", file=sys.stderr)
    elif room_input.startswith("#"):
        # Room alias
        try:
            room_id = resolve_room_alias(config, room_input)
            if args.debug:
                print(f"Resolved {room_input} -> {room_id}", file=sys.stderr)
        except ValueError as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Room name lookup
        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room_id = found_id
            if args.debug:
                print(f"Found room: {room_id}", file=sys.stderr)
        else:
            error_msg = f"Could not find room '{room_input}'"
            if matches:
                error_msg += f". Multiple matches found:\n"
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
            else:
                error_msg += ". Use 'matrix-rooms.py' to list available rooms."
            if args.json:
                print(json.dumps({"error": error_msg}))
            else:
                print(f"Error: {error_msg}", file=sys.stderr)
            sys.exit(1)

    # Send reaction
    result = send_reaction(config, room_id, args.event_id, args.emoji)

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    elif args.quiet:
        print(result.get("event_id", ""))
    else:
        print(f"Reacted with {args.emoji} to {args.event_id}")
        print(f"Event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
