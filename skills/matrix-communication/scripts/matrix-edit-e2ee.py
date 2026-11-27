#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Edit one of your own messages in a Matrix room (E2EE when the room is).

Runs `matrix-e2ee-cli edit`.

Usage:
    matrix-edit-e2ee.py ROOM EVENT_ID NEW_MESSAGE [--no-prefix] [--json] [--quiet]

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
        description="Edit a message in an E2EE Matrix room"
    )
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("event_id", help="Event ID to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument(
        "--no-prefix", action="store_true", help="Do not add bot_prefix"
    )
    parser.add_argument(
        "--trust-unverified-devices",
        action="store_true",
        help="Share this edit's room key with unverified devices too",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Print only the edit's event id"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["edit"]
    for flag in ("no_prefix", "trust_unverified_devices", "json", "quiet"):
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
