#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""React to a Matrix message: add, remove, swap or list your own reactions.

Runs `matrix-e2ee-cli react` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-react.py ROOM EVENT_ID EMOJI [EMOJI ...] [--replace OLD ...]
    matrix-react.py ROOM EVENT_ID EMOJI [EMOJI ...] --remove
    matrix-react.py ROOM EVENT_ID --list

Several EMOJI are set in one call, in the order given. --replace is a status
swap: set EMOJI, then remove this account's own reactions with any of OLD on
the same event (after the last EMOJI). The account's own reactions are looked
up on the server, so no reaction id is needed. Prints "Reacted with … to …" and
"Event ID: $…" per EMOJI (--quiet: the ids alone, --json: JSON); --list prints
"EMOJI<TAB>reaction event id" per own reaction.

Reactions are sent unencrypted, also in an encrypted room, so
--trust-unverified-devices shares no key; it is accepted for old callers.
--debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="React to a Matrix message with an emoji"
    )
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("event_id", help="Event ID of the message to react to")
    parser.add_argument("emoji", nargs="*", help="Reaction key(s); not with --list")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--replace",
        nargs="+",
        default=[],
        metavar="OLD",
        help="Status swap: remove own OLD after setting EMOJI",
    )
    mode.add_argument(
        "--remove",
        action="store_true",
        help="Remove own EMOJI reactions instead of adding them",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="List own reactions on the event; changes nothing",
    )
    parser.add_argument(
        "--trust-unverified-devices",
        action="store_true",
        help="Accepted for old callers; no effect (reactions are sent unencrypted)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Print only the reaction event ids"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.list and args.emoji:
        raise Unsupported("--list takes no EMOJI")
    if not args.list and not args.emoji:
        raise Unsupported("EMOJI is required unless --list is given")
    cli = ["react"]
    for flag in ("remove", "list", "trust_unverified_devices", "json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag.replace("_", "-"))
    if args.replace:
        cli += ["--replace", *args.replace]
    cli += [
        "--",
        normalize_room_input(clean_message(args.room)),
        args.event_id,
        *args.emoji,
    ]
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
