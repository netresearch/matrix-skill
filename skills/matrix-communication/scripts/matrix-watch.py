#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Follow a watched room's log: what is new since the cursor, then live.

Runs `matrix-e2ee-cli watch`; needs `matrix-watchd.py` and the room in
"watch_rooms". ROOM is a room ID, or the alias or name as written in
"watch_rooms".

Usage:
    matrix-watch.py ROOM [--cursor NAME] [--no-summary] [--once]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.wrapper import Unsupported, refuse, run_cli

# Ctrl-C: the runner's 130, or a child killed by SIGINT.
INTERRUPTED = {130, -2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Follow a room's event log")
    parser.add_argument("room", help='Room ID, or alias or name as in "watch_rooms"')
    parser.add_argument(
        "--cursor", help="Name this reader's position (default: default)"
    )
    parser.add_argument(
        "--no-summary", action="store_true", help="Skip the 'since last' line"
    )
    parser.add_argument(
        "--once", action="store_true", help="Print what is new and exit"
    )
    return parser


def translate(args):
    cli = ["watch"]
    if args.cursor:
        cli.append(f"--cursor={args.cursor}")  # "=": a "-" start stays a value
    if args.no_summary:
        cli.append("--no-summary")
    if args.once:
        cli.append("--once")
    cli += ["--", normalize_room_input(args.room)]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    sys.stdout.flush()
    code = run_cli(cli_args, extra_env)
    if not args.once and code in INTERRUPTED:
        code = 0  # Ctrl-C is how following ends, as before
    sys.exit(code)


if __name__ == "__main__":
    main()
