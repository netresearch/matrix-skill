#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Show or set a user's power level in a Matrix room.

Usage:
    matrix-power-level.py ROOM --show
    matrix-power-level.py ROOM --get USER_ID
    matrix-power-level.py ROOM --set USER_ID LEVEL
    matrix-power-level.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server (resolved via directory)
                - Room name: "agent-work" (looked up from joined rooms)

Options:
    --show            Print the full m.room.power_levels event content
    --get USER_ID     Print USER_ID's current power level (falls back to
                      users_default if not listed explicitly)
    --set USER_ID LEVEL
                      Set USER_ID's power level to LEVEL (integer, commonly
                      0=user, 50=moderator, 100=admin — any int is valid)
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help

Power levels are a single room state event: setting one user's level requires
reading the whole event, changing just that user's entry, and writing the
whole event back (a PUT replaces the entire content — there is no merge on
the server side). --set does this GET-modify-PUT for you. The acting user
(the bot) needs a power level >= the level being granted and >= the target's
current level, otherwise the homeserver rejects the change with M_FORBIDDEN.

On newer room versions the room creator has implicit, permanent authority
and must NOT appear in content.users — the server rejects an attempt to set
the creator's own level with "Creator user must not appear in content.users".
This is expected: don't try to promote/demote the creator, only other members.

Examples:
    # Inspect current power levels before changing anything
    matrix-power-level.py "LSB Project" --show

    # Check one user's level
    matrix-power-level.py "LSB Project" --get '@jane.doe:netresearch.de'

    # Promote a user to moderator
    matrix-power-level.py "LSB Project" --set '@jane.doe:netresearch.de' 50

    # Promote a user to admin
    matrix-power-level.py '!abc123:netresearch.de' --set '@jane.doe:netresearch.de' 100
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


def get_power_levels(config: dict, room_id: str) -> dict:
    """Fetch the current m.room.power_levels state event content.

    Returns:
        The power_levels content dict, or a dict with 'error' on failure.
    """
    return matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.power_levels/")


def set_power_level(config: dict, room_id: str, user_id: str, level: int) -> dict:
    """Set a single user's power level via GET-modify-PUT.

    The power_levels state event has one state key (empty string) holding
    the whole permission model. Setting one user's level means fetching the
    current content, mutating its "users" dict in place, and PUTting the
    complete object back — a partial PUT would silently wipe every other
    key (events, state_default, ban/kick/redact/invite, other users' levels).
    """
    content = get_power_levels(config, room_id)
    if "error" in content:
        return content

    content.setdefault("users", {})
    previous = content["users"].get(user_id, content.get("users_default", 0))
    content["users"][user_id] = level

    result = matrix_request(
        config, "PUT", f"/rooms/{room_id}/state/m.room.power_levels/", content
    )
    if "error" in result:
        return result

    return {
        "room_id": room_id,
        "user_id": user_id,
        "previous": previous,
        "level": level,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Show or set a user's power level in a Matrix room"
    )
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--show", action="store_true", help="Print the full power_levels event"
    )
    group.add_argument(
        "--get", metavar="USER_ID", help="Print USER_ID's current power level"
    )
    group.add_argument(
        "--set",
        nargs=2,
        metavar=("USER_ID", "LEVEL"),
        help="Set USER_ID's power level to LEVEL",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()
    room_id = resolve_room_cli(config, args.room, args.json, args.debug)

    if args.show:
        result = get_power_levels(config, room_id)
        if "error" in result:
            if args.json:
                print(json.dumps(result))
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=None if args.quiet else 2))
        return

    if args.get:
        result = get_power_levels(config, room_id)
        if "error" in result:
            if args.json:
                print(json.dumps(result))
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        level = result.get("users", {}).get(args.get, result.get("users_default", 0))
        if args.json:
            print(json.dumps({"room_id": room_id, "user_id": args.get, "level": level}))
        elif args.quiet:
            print(level)
        else:
            print(f"{args.get} in {room_id}: {level}")
        return

    # --set
    user_id, level_str = args.set
    try:
        level = int(level_str)
    except ValueError:
        msg = f"LEVEL must be an integer, got {level_str!r}"
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        print(f"Setting {user_id} to power level {level} in {room_id}", file=sys.stderr)

    result = set_power_level(config, room_id, user_id, level)

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    elif args.quiet:
        print(result["level"])
    else:
        print(f"{user_id} in {room_id}: {result['previous']} -> {result['level']}")


if __name__ == "__main__":
    main()
