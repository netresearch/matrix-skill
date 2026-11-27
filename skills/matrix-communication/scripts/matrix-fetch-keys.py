#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Ask your other devices for the room keys this device is missing.

Runs `matrix-e2ee-cli fetch-keys`.

Usage:
    matrix-fetch-keys.py ROOM [--limit N] [--sync-time S]

--debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch missing room keys")
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("--limit", type=int, help="Messages to scan (default: 100)")
    parser.add_argument(
        "--sync-time", type=int, help="Seconds to wait for keys (default: 60)"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["fetch-keys"]
    if args.limit is not None:
        cli += ["--limit", str(args.limit)]
    if args.sync_time is not None:
        cli += ["--sync-time", str(args.sync_time)]
    cli += ["--", normalize_room_input(args.room)]
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
