#!/usr/bin/env python3
"""Redact (delete) a message from a Matrix room.

Usage:
    matrix-redact.py ROOM EVENT_ID [--reason REASON]
    matrix-redact.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)
    EVENT_ID    Event ID of the message to redact ($xxx:server)

Options:
    --reason    Reason for redaction (optional)
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help
"""

import json
import sys
import time
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


def matrix_request(config: dict, method: str, endpoint: str, data: dict = None) -> dict:
    """Make a Matrix API request."""
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json"
    }

    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            return {"error": error_json.get("error", error_body), "errcode": error_json.get("errcode")}
        except:
            return {"error": error_body, "errcode": str(e.code)}


def resolve_room_alias(config: dict, alias: str) -> str:
    """Resolve a room alias to room ID."""
    encoded_alias = urllib.parse.quote(alias, safe='')
    result = matrix_request(config, "GET", f"/directory/room/{encoded_alias}")
    if "room_id" in result:
        return result["room_id"]
    raise ValueError(f"Could not resolve room alias: {result.get('error', 'Unknown error')}")


def redact_message(config: dict, room_id: str, event_id: str, reason: str = None) -> dict:
    """Redact a message from a Matrix room."""
    txn_id = str(int(time.time() * 1000))

    data = {}
    if reason:
        data["reason"] = reason

    # URL encode the event_id (it contains special characters like $ and :)
    encoded_event_id = urllib.parse.quote(event_id, safe='')

    return matrix_request(
        config,
        "PUT",
        f"/rooms/{urllib.parse.quote(room_id, safe='')}/redact/{encoded_event_id}/{txn_id}",
        data  # Always pass dict, even if empty - {} is falsy but Matrix needs JSON body
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Redact a message from a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("event_id", help="Event ID of the message to redact")
    parser.add_argument("--reason", help="Reason for redaction")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Resolve room alias if needed
    room_id = args.room
    if args.room.startswith("#"):
        try:
            room_id = resolve_room_alias(config, args.room)
            if args.debug:
                print(f"Resolved {args.room} -> {room_id}", file=sys.stderr)
        except ValueError as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Redact message
    result = redact_message(config, room_id, args.event_id, args.reason)

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
        print(f"Message redacted from {args.room}")
        print(f"Redaction event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
