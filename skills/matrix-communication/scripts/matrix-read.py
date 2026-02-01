#!/usr/bin/env python3
"""Read recent messages from a Matrix room.

Note: Only reads unencrypted messages. E2EE messages will show as "[encrypted]".

Usage:
    matrix-read.py ROOM [--limit N] [--json]
    matrix-read.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name

Options:
    --limit N   Number of messages to retrieve [default: 10]
    --json      Output as JSON
    --help      Show this help
"""

import json
import sys
import os
import urllib.parse

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    matrix_request,
    resolve_room_alias,
    find_room_by_name,
    format_timestamp,
    clean_message,
)


def read_messages(config: dict, room_id: str, limit: int = 10) -> list:
    """Read recent messages from a room using sync."""
    # Use sync with a filter for this specific room
    filter_json = json.dumps({
        "room": {
            "rooms": [room_id],
            "timeline": {"limit": limit}
        }
    })
    encoded_filter = urllib.parse.quote(filter_json, safe='')

    result = matrix_request(config, "GET", f"/sync?timeout=0&full_state=true&filter={encoded_filter}")

    if "error" in result:
        return []

    messages = []
    room_data = result.get("rooms", {}).get("join", {}).get(room_id, {})
    events = room_data.get("timeline", {}).get("events", [])

    for event in events:
        if event.get("type") == "m.room.message":
            content = event.get("content", {})
            messages.append({
                "sender": event.get("sender", "unknown"),
                "body": content.get("body", ""),
                "msgtype": content.get("msgtype", "m.text"),
                "timestamp": event.get("origin_server_ts", 0),
                "event_id": event.get("event_id"),
            })
        elif event.get("type") == "m.room.encrypted":
            messages.append({
                "sender": event.get("sender", "unknown"),
                "body": "[encrypted]",
                "msgtype": "m.room.encrypted",
                "timestamp": event.get("origin_server_ts", 0),
                "event_id": event.get("event_id"),
            })

    return messages


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Read recent messages from a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server), room ID (!id:server), or room name")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of messages (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    config = load_config()

    # Clean and resolve room
    room_input = clean_message(args.room)
    room_id = room_input

    if room_input.startswith("!"):
        # Direct room ID
        room_id = room_input
    elif room_input.startswith("#"):
        # Room alias
        try:
            room_id = resolve_room_alias(config, room_input)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Room name lookup
        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room_id = found_id
        else:
            error_msg = f"Could not find room '{room_input}'"
            if matches:
                error_msg += f". Multiple matches found:\n"
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
            else:
                error_msg += ". Use 'matrix-rooms.py' to list available rooms."
            print(f"Error: {error_msg}", file=sys.stderr)
            sys.exit(1)

    messages = read_messages(config, room_id, args.limit)

    if args.json:
        print(json.dumps(messages, indent=2))
    else:
        if not messages:
            print("No messages found (or all messages are encrypted)")
            return

        for msg in messages:
            ts = format_timestamp(msg["timestamp"])
            sender = msg["sender"].split(":")[0].lstrip("@")
            body = msg["body"][:100] + "..." if len(msg["body"]) > 100 else msg["body"]
            print(f"[{ts}] {sender}: {body}")


if __name__ == "__main__":
    main()
