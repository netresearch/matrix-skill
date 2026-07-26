#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Invite a user to a Matrix room.

Usage:
    matrix-invite.py ROOM USER_ID [OPTIONS]
    matrix-invite.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server (resolved via directory)
                - Room name: "agent-work" (looked up from joined rooms)
    USER_ID     Full Matrix user ID to invite (e.g. @jane.doe:netresearch.de)

Options:
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help

Examples:
    # Invite by room name
    matrix-invite.py "LSB Project" '@jane.doe:netresearch.de'

    # Invite by room ID
    matrix-invite.py '!abc123:netresearch.de' '@jane.doe:netresearch.de'
"""

import json
import os
import sys

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    matrix_request,
    resolve_room_cli,
)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def invite_user(config: dict, room_id: str, user_id: str) -> dict:
    """Invite a user to a Matrix room.

    Args:
        config: Matrix config with homeserver and access_token
        room_id: Room ID to invite to
        user_id: Full Matrix user ID (e.g. @user:server)

    Returns:
        Empty dict on success (per Matrix spec), or dict with 'error' on failure
    """
    return matrix_request(
        config, "POST", f"/rooms/{room_id}/invite", {"user_id": user_id}
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Invite a user to a Matrix room")
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    parser.add_argument("user_id", help="Matrix user ID to invite (@user:server)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()
    room_id = resolve_room_cli(config, args.room, args.json, args.debug)

    if args.debug:
        print(f"Inviting {args.user_id} to {room_id}", file=sys.stderr)

    result = invite_user(config, room_id, args.user_id)

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps({"room_id": room_id, "user_id": args.user_id}))
    elif args.quiet:
        print(room_id)
    else:
        print(f"Invited {args.user_id} to {room_id}")


if __name__ == "__main__":
    main()
