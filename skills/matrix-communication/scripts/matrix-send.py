#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Send a message to a Matrix room.

Runs `matrix-e2ee-cli send` (see _lib/cli.py for how the binary is found):
encrypted when the room is encrypted, unencrypted when it is not.
matrix-send-e2ee.py runs the same command and has more options (--to,
--mention, ...).

Usage:
    matrix-send.py ROOM MESSAGE [OPTIONS]
    matrix-send.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server
                - Room name: "agent-work" (looked up among the joined rooms;
                  a message needs the exact name, no partial match)
                - matrix.to link
    MESSAGE     Message content (markdown supported)

Options:
    --format FORMAT   markdown (the default, and the only format left):
                      --format text is refused, matrix-e2ee-cli always
                      renders Markdown
    --emote           Send as /me action (m.emote)
    --notice          Send as m.notice — bot-flagged, suppressed from auto-reply
                      loops. Use for unattended automation. Mutually exclusive
                      with --emote.
    --thread EVENT    Reply in thread (event ID of thread root)
    --reply EVENT     Reply to message (event ID to reply to)
    --no-prefix       Don't add bot_prefix from config
    --plaintext       Send unencrypted, also in an encrypted room, where the
                      homeserver and everyone who joins later can read it:
                      only for a bot that cannot decrypt, such as a
                      matrix-hookshot bridge without encryption
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Accepted and ignored
    --help            Show this help

Effects (Element clients):
    Include emoji in message to trigger visual effects:
    party or tada = confetti, fireworks = fireworks, snowflake = snowfall

Examples:
    # Send by room name (easiest)
    matrix-send.py agent-work "Hello team!"

    # Send by room ID (from matrix-rooms.py output)
    matrix-send.py '!sZBoTOreI1z0BgHY-s2ZC9MV63B1orGFigPXvYMQ22E' "Hello!"

    # Send by alias
    matrix-send.py '#general:matrix.org' "Hello everyone!"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, refuse, room_chooser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a message to a Matrix room")
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    parser.add_argument("message", help="Message content (markdown supported)")
    parser.add_argument(
        "--format",
        choices=["text", "markdown"],
        default="markdown",
        help="Message format: markdown (text is refused)",
    )
    msgtype_group = parser.add_mutually_exclusive_group()
    msgtype_group.add_argument(
        "--emote", action="store_true", help="Send as /me action (m.emote msgtype)"
    )
    msgtype_group.add_argument(
        "--notice",
        action="store_true",
        help="Send as m.notice — bot-flagged, suppressed from auto-reply loops. "
        "Use for unattended automation (release announcements, CI summaries).",
    )
    parser.add_argument(
        "--thread", metavar="EVENT_ID", help="Reply in thread (event ID of thread root)"
    )
    parser.add_argument(
        "--reply", metavar="EVENT_ID", help="Reply to message (event ID)"
    )
    parser.add_argument(
        "--no-prefix", action="store_true", help="Don't add bot_prefix from config"
    )
    parser.add_argument(
        "--plaintext",
        action="store_true",
        help="Send unencrypted, also in an encrypted room: only for a bot that cannot decrypt, such as a hookshot bridge without encryption; the homeserver and everyone who joins later can read this message",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.format == "text":
        # matrix-e2ee-cli sends an HTML body whenever the Markdown renders to
        # more than its text, and has no switch for plain text.
        raise Unsupported(
            "--format text has no equivalent in matrix-e2ee-cli, which always "
            "renders Markdown; send without --format"
        )
    cli = ["send"]
    for flag in ("emote", "notice", "no_prefix", "plaintext", "json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag.replace("_", "-"))
    for flag in ("thread", "reply"):
        if getattr(args, flag):
            cli += ["--" + flag, getattr(args, flag)]
    # Before "--": with an optional ROOM, clap puts everything after "--" into
    # MESSAGE.
    room = normalize_room_input(clean_message(args.room))
    # A shorthand such as "-ops" stands here only until room_chooser puts the
    # room ID in its place; nothing unresolved reaches the CLI.
    cli += [room, "--", clean_message(args.message)]
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
        choose=room_chooser(cli_args[cli_args.index("--") - 1], write=True),
        json_errors=args.json,
    )


if __name__ == "__main__":
    main()
