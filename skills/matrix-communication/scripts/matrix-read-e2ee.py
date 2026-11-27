#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read the last messages of a Matrix room, decrypted.

Runs `matrix-e2ee-cli read`. --json prints the same JSON array as before;
each message also carries `decrypted`, `sender_verified` and `room_encrypted`
(matrix-e2ee-cli 0.3.0), which callers that read known keys can ignore.

Usage:
    matrix-read-e2ee.py ROOM [--limit N] [--json] [--request-keys]

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
        description="Read messages from an E2EE Matrix room"
    )
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument(
        "--limit", "-l", type=int, help="Number of messages (default: 10)"
    )
    parser.add_argument(
        "--request-keys",
        "-k",
        action="store_true",
        help="Ask your other devices for missing keys, then read again",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["read"]
    if args.limit is not None:
        cli += ["--limit", str(args.limit)]
    if args.request_keys:
        cli.append("--request-keys")
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
    )


if __name__ == "__main__":
    main()
