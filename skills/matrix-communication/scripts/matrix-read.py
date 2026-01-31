#!/usr/bin/env python3
"""Read recent messages from a Matrix room.

Note: Only reads unencrypted messages. E2EE messages will show as "[encrypted]".

Usage:
    matrix-read.py ROOM [--limit N] [--json]
    matrix-read.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)

Options:
    --limit N   Number of messages to retrieve [default: 10]
    --json      Output as JSON
    --help      Show this help
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
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
            return {"error": error_json.get("error", error_body), "errcode": error_json.get("errcode")}
        except:
            return {"error": error_body}


def resolve_room_alias(config: dict, alias: str) -> str:
    """Resolve a room alias to room ID."""
    encoded_alias = urllib.parse.quote(alias, safe='')
    result = matrix_request(config, "GET", f"/directory/room/{encoded_alias}")
    if "room_id" in result:
        return result["room_id"]
    raise ValueError(f"Could not resolve room alias: {result.get('error', 'Unknown error')}")


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
                "timestamp": event.get("origin_server_ts", 0)
            })
        elif event.get("type") == "m.room.encrypted":
            messages.append({
                "sender": event.get("sender", "unknown"),
                "body": "[encrypted]",
                "msgtype": "m.room.encrypted",
                "timestamp": event.get("origin_server_ts", 0)
            })

    return messages


def format_timestamp(ts: int) -> str:
    """Format timestamp to readable string."""
    from datetime import datetime
    if ts == 0:
        return "unknown"
    dt = datetime.fromtimestamp(ts / 1000)
    return dt.strftime("%Y-%m-%d %H:%M")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Read recent messages from a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of messages (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    config = load_config()

    # Resolve room alias if needed
    room_id = args.room
    if args.room.startswith("#"):
        try:
            room_id = resolve_room_alias(config, args.room)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
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
