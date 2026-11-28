#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Invite a user to a Matrix room.

Runs `matrix-e2ee-cli invite` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-invite.py ROOM USER_ID [OPTIONS]
    matrix-invite.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server
                - Room name: "agent-work" (looked up among the joined rooms;
                  an invitation needs the exact name, no partial match)
                - matrix.to link
    USER_ID     Full Matrix user ID to invite (e.g. @jane.doe:netresearch.de)

Options:
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Accepted and ignored
    --help      Show this help

Examples:
    # Invite by room name
    matrix-invite.py "LSB Project" '@jane.doe:netresearch.de'

    # Invite by room ID
    matrix-invite.py '!abc123:netresearch.de' '@jane.doe:netresearch.de'
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invite a user to a Matrix room")
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    parser.add_argument("user_id", help="Matrix user ID to invite (@user:server)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["invite"]
    for flag in ("json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag)
    cli += ["--", normalize_room_input(clean_message(args.room)), args.user_id]
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
        choose=room_chooser(cli_args[cli_args.index("--") + 1], write=True),
        json_errors=args.json,
    )


if __name__ == "__main__":
    main()
