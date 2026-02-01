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
import sys
import os

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import load_config, matrix_request, resolve_room_alias


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

    try:
        room_id = resolve_room_alias(config, args.alias)
        result = {"room_id": room_id, "alias": args.alias}

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Alias: {args.alias}")
            print(f"Room ID: {room_id}")

    except ValueError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
