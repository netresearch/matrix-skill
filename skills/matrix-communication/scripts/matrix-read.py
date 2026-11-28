#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read recent messages from a Matrix room.

Runs `matrix-e2ee-cli read` (see _lib/cli.py for how the binary is found):
the same command as matrix-read-e2ee.py, so encrypted messages are decrypted
where the device holds their keys. Messages are listed newest first, in the
format of matrix-read-e2ee.py.

Usage:
    matrix-read.py ROOM [--limit N] [--json]
    matrix-read.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), room name or
                matrix.to link

Options:
    --limit N   Number of messages to retrieve [default: 10]
    --json      Output as JSON
    --help      Show this help

--debug is accepted and ignored.
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
        description="Read recent messages from a Matrix room"
    )
    parser.add_argument(
        "room", help="Room alias (#room:server), room ID (!id:server), or room name"
    )
    parser.add_argument(
        "--limit", "-l", type=int, help="Number of messages (default: 10)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["read"]
    if args.limit is not None:
        cli += ["--limit", str(args.limit)]
    if args.json:
        cli.append("--json")
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
        choose=room_chooser(cli_args[cli_args.index("--") + 1]),
        json_errors=False,
    )


if __name__ == "__main__":
    main()
