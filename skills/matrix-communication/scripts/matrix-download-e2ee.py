#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Download the attachment of a file, image, video or audio message.

Runs `matrix-e2ee-cli download`. An existing file is never replaced.

Usage:
    matrix-download-e2ee.py ROOM EVENT_ID [--output DIR] [--filename NAME]

--overwrite is refused: the CLI has no way to replace a file. --debug is
accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download media from a Matrix room")
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("event_id", help="Event ID of the media message")
    parser.add_argument("--output", help="Output directory [default: .]")
    parser.add_argument("--filename", help="Override filename")
    parser.add_argument(
        "--overwrite", action="store_true", help="Refused (see the docstring)"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.overwrite:
        raise Unsupported(
            "--overwrite is not supported any more: matrix-e2ee-cli never replaces a file. "
            "Remove the old file first, or pick another --filename or --output"
        )
    cli = ["download"]
    if args.output:
        cli += ["--output", args.output]
    if args.filename:
        cli += ["--filename", args.filename]
    cli += ["--", normalize_room_input(args.room), args.event_id]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env)


if __name__ == "__main__":
    main()
