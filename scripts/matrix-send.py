#!/usr/bin/env python3
"""Send a message to a Matrix room.

Usage:
    matrix-send.py ROOM MESSAGE [--format FORMAT]
    matrix-send.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)
    MESSAGE     Message content (markdown supported)

Options:
    --format FORMAT   Message format: text or markdown [default: markdown]
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help
"""

import json
import os
import re
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
        print("Create it with:", file=sys.stderr)
        print(json.dumps({
            "homeserver": "https://matrix.netresearch.de",
            "access_token": "syt_..."
        }, indent=2), file=sys.stderr)
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

    body = json.dumps(data).encode() if data else None
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


def markdown_to_html(text: str) -> str:
    """Convert simple markdown to Matrix HTML."""
    html = text

    # Bold: **text** -> <strong>text</strong>
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

    # Italic: *text* -> <em>text</em>
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Code: `text` -> <code>text</code>
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)

    # Lists: - item -> <ul><li>item</li></ul>
    lines = html.split('\n')
    in_list = False
    result = []
    for line in lines:
        if line.strip().startswith('- '):
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append(f'<li>{line.strip()[2:]}</li>')
        else:
            if in_list:
                result.append('</ul>')
                in_list = False
            result.append(line)
    if in_list:
        result.append('</ul>')
    html = '\n'.join(result)

    # Newlines to <br>
    html = html.replace('\n', '<br>')

    return html


def send_message(config: dict, room_id: str, message: str, format: str = "markdown") -> dict:
    """Send a message to a Matrix room."""
    txn_id = str(int(time.time() * 1000))

    content = {
        "msgtype": "m.text",
        "body": message
    }

    if format == "markdown":
        html = markdown_to_html(message)
        if html != message:  # Only add HTML if there's actual formatting
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html

    return matrix_request(config, "PUT", f"/rooms/{room_id}/send/m.room.message/{txn_id}", content)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send a message to a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("message", help="Message content (markdown supported)")
    parser.add_argument("--format", choices=["text", "markdown"], default="markdown",
                        help="Message format (default: markdown)")
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

    # Send message
    result = send_message(config, room_id, args.message, args.format)

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
