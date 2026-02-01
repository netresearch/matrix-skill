#!/usr/bin/env python3
"""Edit an existing message in a Matrix room.

Usage:
    matrix-edit.py ROOM EVENT_ID NEW_MESSAGE
    matrix-edit.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name
    EVENT_ID    Event ID of the message to edit ($xxx:server)
    NEW_MESSAGE The new message content (replaces original)

Options:
    --no-prefix Don't add bot_prefix from config
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help
"""

import json
import sys
import os
import time
import urllib.parse

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    matrix_request,
    resolve_room_alias,
    find_room_by_name,
    markdown_to_html,
    add_bot_prefix,
    clean_message,
)


def edit_message(config: dict, room_id: str, event_id: str, new_message: str) -> dict:
    """Edit an existing message in a Matrix room."""
    txn_id = str(int(time.time() * 1000))

    # Build the replacement content
    content = {
        "msgtype": "m.text",
        "body": f"* {new_message}",  # Prefix with * for fallback
        "m.new_content": {
            "msgtype": "m.text",
            "body": new_message,
        },
        "m.relates_to": {
            "rel_type": "m.replace",
            "event_id": event_id,
        }
    }

    # Add HTML formatting
    html = markdown_to_html(new_message)
    if html != new_message:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = f"* {html}"
        content["m.new_content"]["format"] = "org.matrix.custom.html"
        content["m.new_content"]["formatted_body"] = html

    return matrix_request(
        config,
        "PUT",
        f"/rooms/{urllib.parse.quote(room_id, safe='')}/send/m.room.message/{txn_id}",
        content
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Edit a message in a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server), room ID (!id:server), or room name")
    parser.add_argument("event_id", help="Event ID of the message to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument("--no-prefix", action="store_true",
                        help="Don't add bot_prefix from config")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Clean message
    message = clean_message(args.message)

    # Add bot prefix if configured (unless --no-prefix)
    if not args.no_prefix and config.get("bot_prefix"):
        message = add_bot_prefix(message, config["bot_prefix"])

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

    # Edit message
    result = edit_message(config, room_id, args.event_id, message)

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
        print(f"Message edited in {args.room}")
        print(f"Edit event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
