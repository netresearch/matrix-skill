#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Edit an existing message in a Matrix room.

Runs `matrix-e2ee-cli edit` (see _lib/cli.py for how the binary is found):
encrypted when the room is encrypted. The message must be one of your own.

Usage:
    matrix-edit.py ROOM EVENT_ID NEW_MESSAGE
    matrix-edit.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), room name
                (exact, no partial match) or matrix.to link
    EVENT_ID    Event ID of the message to edit ($xxx:server)
    NEW_MESSAGE The new message content (replaces original)

Options:
    --no-prefix Don't add bot_prefix from config
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Accepted and ignored
    --help      Show this help
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Edit a message in a Matrix room")
    parser.add_argument(
        "room", help="Room alias (#room:server), room ID (!id:server), or room name"
    )
    parser.add_argument("event_id", help="Event ID of the message to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument(
        "--no-prefix", action="store_true", help="Don't add bot_prefix from config"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["edit"]
    for flag in ("no_prefix", "json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag.replace("_", "-"))
    cli += [
        "--",
        normalize_room_input(clean_message(args.room)),
        args.event_id,
        clean_message(args.message),
    ]
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
