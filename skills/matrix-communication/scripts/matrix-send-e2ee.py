#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Send a message to a Matrix room, end-to-end encrypted when the room is.

Runs `matrix-e2ee-cli send` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-send-e2ee.py ROOM MESSAGE [OPTIONS]
    matrix-send-e2ee.py --to @user:server MESSAGE [OPTIONS]

ROOM: room ID (!id:server), alias (#room:server), room name or matrix.to link.
MESSAGE: Markdown. Prints "Event ID: $..." (--quiet: the id alone, --json: JSON).
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
        description="Send a message to a Matrix room (E2EE)"
    )
    parser.add_argument(
        "room", nargs="?", help="Room ID, alias, name or matrix.to link; omit with --to"
    )
    parser.add_argument("message", help="Message content (Markdown)")
    parser.add_argument(
        "--to",
        metavar="@user:server",
        help="Send to the existing direct chat with this user",
    )
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--emote", action="store_true", help="Send as m.emote")
    kind.add_argument(
        "--notice", action="store_true", help="Send as m.notice (automation)"
    )
    parser.add_argument(
        "--thread", metavar="EVENT_ID", help="Reply in the thread of this root event"
    )
    parser.add_argument("--reply", metavar="EVENT_ID", help="Reply to this event")
    parser.add_argument(
        "--no-prefix", action="store_true", help="Do not add bot_prefix from config"
    )
    parser.add_argument(
        "--mention",
        action="append",
        metavar="@user:server",
        help="Notify this user (repeatable)",
    )
    parser.add_argument(
        "--mention-room",
        action="store_true",
        help="Notify everyone in the room (@room)",
    )
    parser.add_argument(
        "--trust-unverified-devices",
        action="store_true",
        help="Share this message's room key with unverified devices too",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Print only the event id"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if (args.room is None) == (args.to is None):
        raise Unsupported("give exactly one of ROOM or --to @user:server")
    cli = ["send"]
    if args.to:
        cli += ["--to", args.to]
    for flag in (
        "emote",
        "notice",
        "no_prefix",
        "mention_room",
        "trust_unverified_devices",
        "json",
        "quiet",
    ):
        if getattr(args, flag):
            cli.append("--" + flag.replace("_", "-"))
    for flag in ("thread", "reply"):
        if getattr(args, flag):
            cli += ["--" + flag, getattr(args, flag)]
    for user in args.mention or []:
        cli += ["--mention", user]
    if args.room is not None:
        # Before "--": with an optional ROOM, clap puts everything after "--"
        # into MESSAGE.
        room = normalize_room_input(clean_message(args.room))
        if room.startswith("-"):
            # Placed before "--", it would be read as a CLI flag.
            raise Unsupported(f"room {room!r} starts with '-'; that is no room")
        cli.append(room)
    cli += ["--", clean_message(args.message)]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_intermixed_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    choose = None
    if args.room is not None:
        choose = room_chooser(cli_args[cli_args.index("--") - 1], write=True)
    exit_with(cli_args, extra_env, choose=choose, json_errors=args.json)


if __name__ == "__main__":
    main()
