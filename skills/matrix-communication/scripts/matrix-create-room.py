#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Create a new Matrix room.

Usage:
    matrix-create-room.py NAME [OPTIONS]
    matrix-create-room.py --help

Arguments:
    NAME        Room display name

Options:
    --alias LOCALPART   Room alias localpart, e.g. "lsb" -> #lsb:server
                        (fails if the alias is already taken)
    --topic TOPIC       Room topic
    --invite USER_ID    Invite a user on creation (repeatable)
    --preset PRESET     private_chat (default) | public_chat | trusted_private_chat
    --json              Output as JSON
    --quiet             Minimal output (just the room ID)
    --debug             Show debug information

Examples:
    # Minimal private room
    matrix-create-room.py "LSB Project"

    # With alias and initial invites
    matrix-create-room.py "LSB Project" --alias lsb \\
        --invite '@tobias.hein:netresearch.de' --invite '@jane.doe:netresearch.de'

    # Public room with topic
    matrix-create-room.py "LSB Project" --topic "Landessportbund onboarding" \\
        --preset public_chat
"""

import json
import os
import sys

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import load_config, matrix_request

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def create_room(
    config: dict,
    name: str,
    alias: str | None = None,
    topic: str | None = None,
    invite: list[str] | None = None,
    preset: str = "private_chat",
) -> dict:
    """Create a Matrix room.

    Args:
        config: Matrix config with homeserver and access_token
        name: Room display name
        alias: Room alias localpart (without # or :server)
        topic: Room topic
        invite: List of user IDs to invite on creation
        preset: Room preset (private_chat, public_chat, trusted_private_chat)

    Returns:
        Response dict with 'room_id' on success, or 'error' on failure
    """
    content = {"name": name, "preset": preset}
    if alias:
        content["room_alias_name"] = alias
    if topic:
        content["topic"] = topic
    if invite:
        content["invite"] = invite

    return matrix_request(config, "POST", "/createRoom", content)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Create a new Matrix room")
    parser.add_argument("name", help="Room display name")
    parser.add_argument(
        "--alias", metavar="LOCALPART", help="Room alias localpart (e.g. 'lsb')"
    )
    parser.add_argument("--topic", help="Room topic")
    parser.add_argument(
        "--invite",
        metavar="USER_ID",
        action="append",
        help="Invite a user on creation (repeatable)",
    )
    parser.add_argument(
        "--preset",
        choices=["private_chat", "public_chat", "trusted_private_chat"],
        default="private_chat",
        help="Room preset (default: private_chat)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    if args.debug:
        print(
            f"Creating room name={args.name!r} alias={args.alias!r} "
            f"preset={args.preset} invite={args.invite}",
            file=sys.stderr,
        )

    result = create_room(
        config,
        args.name,
        alias=args.alias,
        topic=args.topic,
        invite=args.invite,
        preset=args.preset,
    )

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    elif args.quiet:
        print(result.get("room_id", ""))
    else:
        print(f"Room created: {result.get('room_id')}")
        if args.alias:
            # Room aliases live on the user's server_name (from user_id),
            # not the homeserver URL — these differ when the homeserver is
            # reached via a delegated/well-known domain (e.g. homeserver
            # https://matrix.example.com but server_name example.com).
            user_id = config.get("user_id")
            if not user_id:
                whoami = matrix_request(config, "GET", "/account/whoami")
                user_id = whoami.get("user_id")
            if user_id:
                server_name = user_id.split(":", 1)[-1]
                print(f"Alias: #{args.alias}:{server_name}")


if __name__ == "__main__":
    main()
