#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create a new Matrix room.

Runs `matrix-e2ee-cli create-room` (see _lib/cli.py for how the binary is
found). The room is unencrypted unless the homeserver's defaults encrypt it.

Usage:
    matrix-create-room.py NAME [OPTIONS]
    matrix-create-room.py --help

Arguments:
    NAME        Room display name

Options:
    --alias LOCALPART   Room alias localpart, e.g. "lsb" -> #lsb:server
                        (fails if the alias is already taken)
    --topic TOPIC       Room topic
    --invite USER_ID    Invite a user on creation (repeatable)
    --preset PRESET     private_chat (default) | public_chat | trusted_private_chat
    --json              Output as JSON
    --quiet             Minimal output (just the room ID)
    --debug             Accepted and ignored

Examples:
    # Minimal private room
    matrix-create-room.py "LSB Project"

    # With alias and initial invites
    matrix-create-room.py "LSB Project" --alias lsb \\
        --invite '@tobias.hein:netresearch.de' --invite '@jane.doe:netresearch.de'

    # Public room with topic
    matrix-create-room.py "LSB Project" --topic "Landessportbund onboarding" \\
        --preset public_chat
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse

PRESETS = ["private_chat", "public_chat", "trusted_private_chat"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a new Matrix room")
    parser.add_argument("name", help="Room display name")
    parser.add_argument(
        "--alias", metavar="LOCALPART", help="Room alias localpart (e.g. 'lsb')"
    )
    parser.add_argument("--topic", help="Room topic")
    parser.add_argument(
        "--invite",
        metavar="USER_ID",
        action="append",
        help="Invite a user on creation (repeatable)",
    )
    parser.add_argument(
        "--preset",
        choices=PRESETS,
        default="private_chat",
        help="Room preset (default: private_chat)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["create-room"]
    # Attached with "=", so a value that starts with "-" stays a value.
    for flag in ("alias", "topic"):
        if getattr(args, flag) is not None:
            cli.append(f"--{flag}={getattr(args, flag)}")
    for user in args.invite or []:
        cli.append(f"--invite={user}")
    cli.append(f"--preset={args.preset}")
    for flag in ("json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag)
    cli += ["--", args.name]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env, json_errors=args.json)


if __name__ == "__main__":
    main()
