#!/usr/bin/env python3
"""Resolve a Matrix room alias to room ID.

Usage:
    matrix-resolve.py ALIAS [--json]
    matrix-resolve.py --help

Arguments:
    ALIAS       Room alias (e.g., #myroom:matrix.org)

Options:
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


def resolve_room_alias(config: dict, alias: str) -> dict:
    """Resolve a room alias to room ID."""
    encoded_alias = urllib.parse.quote(alias, safe='')
    return matrix_request(config, "GET", f"/directory/room/{encoded_alias}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Resolve a Matrix room alias to room ID")
    parser.add_argument("alias", help="Room alias (e.g., #myroom:matrix.org)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.alias.startswith("#"):
        print("Error: Alias must start with #", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    result = resolve_room_alias(config, args.alias)

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Alias: {args.alias}")
        print(f"Room ID: {result.get('room_id')}")
        servers = result.get('servers', [])
        if servers:
            print(f"Servers: {', '.join(servers)}")


if __name__ == "__main__":
    main()
