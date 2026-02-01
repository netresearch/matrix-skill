#!/usr/bin/env python3
"""Send a message to a Matrix room.

Usage:
    matrix-send.py ROOM MESSAGE [OPTIONS]
    matrix-send.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server (resolved via directory)
                - Room name: "agent-work" (looked up from joined rooms)
    MESSAGE     Message content (markdown supported)

Options:
    --format FORMAT   Message format: text or markdown [default: markdown]
    --emote           Send as /me action (m.emote)
    --thread EVENT    Reply in thread (event ID of thread root)
    --reply EVENT     Reply to message (event ID to reply to)
    --no-prefix       Don't add bot_prefix from config
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help

Effects (Element clients):
    Include emoji in message to trigger visual effects:
    party or tada = confetti, fireworks = fireworks, snowflake = snowfall

Examples:
    # Send by room name (easiest)
    matrix-send.py agent-work "Hello team!"

    # Send by room ID (from matrix-rooms.py output)
    matrix-send.py '!sZBoTOreI1z0BgHY-s2ZC9MV63B1orGFigPXvYMQ22E' "Hello!"

    # Send by alias
    matrix-send.py '#general:matrix.org' "Hello everyone!"
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
    markdown_to_html,
    add_bot_prefix,
    clean_message,
)


def send_message(config: dict, room_id: str, message: str, format: str = "markdown",
                 emote: bool = False, thread_id: str = None, reply_id: str = None) -> dict:
    """Send a message to a Matrix room.

    Args:
        config: Matrix config with homeserver and access_token
        room_id: Room ID to send to
        message: Message content
        format: "text" or "markdown"
        emote: If True, send as m.emote (/me action)
        thread_id: Event ID of thread root (for thread replies)
        reply_id: Event ID to reply to
    """
    txn_id = str(int(time.time() * 1000))

    content = {
        "msgtype": "m.emote" if emote else "m.text",
        "body": message
    }

    if format == "markdown":
        html = markdown_to_html(message)
        if html != message:  # Only add HTML if there's actual formatting
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html

    # Thread reply (MSC3440)
    if thread_id:
        content["m.relates_to"] = {
            "rel_type": "m.thread",
            "event_id": thread_id,
            "is_falling_back": True,
        }
        # If also replying to a specific message in thread
        if reply_id and reply_id != thread_id:
            content["m.relates_to"]["m.in_reply_to"] = {"event_id": reply_id}
        else:
            content["m.relates_to"]["m.in_reply_to"] = {"event_id": thread_id}

    # Regular reply (not in thread)
    elif reply_id:
        content["m.relates_to"] = {
            "m.in_reply_to": {"event_id": reply_id}
        }

    return matrix_request(config, "PUT", f"/rooms/{room_id}/send/m.room.message/{txn_id}", content)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send a message to a Matrix room")
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    parser.add_argument("message", help="Message content (markdown supported)")
    parser.add_argument("--format", choices=["text", "markdown"], default="markdown",
                        help="Message format (default: markdown)")
    parser.add_argument("--emote", action="store_true",
                        help="Send as /me action (m.emote msgtype)")
    parser.add_argument("--thread", metavar="EVENT_ID",
                        help="Reply in thread (event ID of thread root)")
    parser.add_argument("--reply", metavar="EVENT_ID",
                        help="Reply to message (event ID)")
    parser.add_argument("--no-prefix", action="store_true",
                        help="Don't add bot_prefix from config")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Clean message from bash escaping artifacts
    message = clean_message(args.message)

    # Add bot prefix if configured (unless --no-prefix or emote)
    if not args.no_prefix and not args.emote and config.get("bot_prefix"):
        message = add_bot_prefix(message, config["bot_prefix"])

    # Resolve room to room ID
    room_input = clean_message(args.room)
    room_id = room_input

    if room_input.startswith("!"):
        # Direct room ID - use as-is
        room_id = room_input
        if args.debug:
            print(f"Using room ID directly: {room_id}", file=sys.stderr)

    elif room_input.startswith("#"):
        # Room alias - try to resolve
        try:
            room_id = resolve_room_alias(config, room_input)
            if args.debug:
                print(f"Resolved alias {room_input} -> {room_id}", file=sys.stderr)
        except ValueError:
            # Alias resolution failed - try name lookup as fallback
            alias_name = room_input.split(":")[0].lstrip("#")
            if args.debug:
                print(f"Alias resolution failed, trying name lookup for '{alias_name}'", file=sys.stderr)

            found_id, matches = find_room_by_name(config, alias_name)
            if found_id:
                room_id = found_id
                if args.debug:
                    print(f"Found room by name: {room_id}", file=sys.stderr)
            else:
                error_msg = f"Could not resolve room '{room_input}'"
                if matches:
                    error_msg += f". Multiple matches found:\n"
                    for m in matches:
                        alias_str = f" ({m['alias']})" if m.get("alias") else ""
                        error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
                else:
                    error_msg += ". Room not found in joined rooms."
                if args.json:
                    print(json.dumps({"error": error_msg}))
                else:
                    print(f"Error: {error_msg}", file=sys.stderr)
                sys.exit(1)

    else:
        # Plain name - look up by name
        if args.debug:
            print(f"Looking up room by name: '{room_input}'", file=sys.stderr)

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

    # Send message
    result = send_message(config, room_id, message, args.format,
                         emote=args.emote, thread_id=args.thread, reply_id=args.reply)

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
        print(f"Message sent to {args.room}")
        print(f"Event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
