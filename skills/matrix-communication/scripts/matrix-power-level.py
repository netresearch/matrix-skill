#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Show or set a user's power level in a Matrix room.

Runs `matrix-e2ee-cli power-level` (see _lib/cli.py for how the binary is
found).

Usage:
    matrix-power-level.py ROOM --show
    matrix-power-level.py ROOM --get USER_ID
    matrix-power-level.py ROOM --set USER_ID LEVEL
    matrix-power-level.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server
                - Room name: "agent-work" (looked up among the joined rooms;
                  --set needs the exact name, no partial match)
                - matrix.to link

Options:
    --show            Print the full m.room.power_levels event content
    --get USER_ID     Print USER_ID's current power level (falls back to
                      users_default if not listed explicitly)
    --set USER_ID LEVEL
                      Set USER_ID's power level to LEVEL (integer, commonly
                      0=user, 50=moderator, 100=admin — any int is valid)
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Accepted and ignored
    --help            Show this help

Power levels are a single room state event: setting one user's level requires
reading the whole event, changing just that user's entry, and writing the
whole event back (a PUT replaces the entire content — there is no merge on
the server side). --set does this GET-modify-PUT for you. The acting user
needs a power level >= the level being granted and >= the target's current
level, otherwise the homeserver rejects the change with M_FORBIDDEN.

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

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["power-level"]
    if args.show:
        cli.append("--show")
    elif args.get is not None:
        cli.append(f"--get={args.get}")
    else:
        # Two values: "--set=USER" would leave LEVEL to the next argument.
        cli += ["--set", *args.set]
    for flag in ("json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag)
    cli += ["--", normalize_room_input(clean_message(args.room))]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(
        cli_args,
        extra_env,
        choose=room_chooser(
            cli_args[cli_args.index("--") + 1], write=args.set is not None
        ),
        json_errors=args.json,
    )


if __name__ == "__main__":
    main()
