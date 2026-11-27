#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Redact (delete) an event in a Matrix room, if your power level allows it.

Runs `matrix-e2ee-cli redact` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-redact.py ROOM EVENT_ID [--reason REASON] [--json] [--quiet]

Prints "Message redacted from ROOM" and "Redaction event ID: $…" (--quiet: the
id alone, --json: JSON). --debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Redact a message from a Matrix room")
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("event_id", help="Event ID of the message to redact")
    parser.add_argument("--reason", help="Reason for the redaction, shown to the room")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Print only the redaction's event id"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["redact"]
    if args.reason is not None:
        # Attached with "=", so a reason that starts with "-" stays a value.
        cli.append(f"--reason={args.reason}")
    for flag in ("json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag)
    cli += ["--", normalize_room_input(clean_message(args.room)), args.event_id]
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
        json_errors=args.json,
    )


if __name__ == "__main__":
    main()
