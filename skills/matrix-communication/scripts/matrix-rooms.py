#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""List joined Matrix rooms.

Runs `matrix-e2ee-cli rooms` (see _lib/cli.py for how the binary is found):
the rooms come from the CLI's store after one sync, or from the watch daemon
while it runs.

Usage:
    matrix-rooms.py [--json] [--search TERM]
    matrix-rooms.py --lookup NAME
    matrix-rooms.py --help

Options:
    --json            Output as JSON
    --search TERM     Filter rooms by name or alias; a room without a name
                      (a direct chat) is named after its members and also
                      matches on their user IDs
    --lookup NAME     Find room by name and output room ID (for scripts).
                      It may return a single partial match, and it succeeds
                      when the members of some room could not be read
                      (warning on stderr), so it is not meant to feed a
                      command that writes: pass the name to that command,
                      which looks it up for writing (exact matches only)
    --help            Show this help

--debug is accepted and ignored.

Examples:
    # List all rooms with names, aliases, and IDs
    matrix-rooms.py

    # Search for rooms containing "agent"
    matrix-rooms.py --search agent

    # Find the direct chat with Jane Doe (by display name or user ID)
    matrix-rooms.py --lookup "Jane Doe"
    matrix-rooms.py --search @jane:example.org

    # Get room ID by name (for use in other commands)
    matrix-rooms.py --lookup "agent-work"

    # A command that writes takes the name itself and looks it up for writing
    matrix-send.py agent-work "Hello!"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List joined Matrix rooms")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--search", "-s", help="Filter rooms by name, alias or member user ID"
    )
    parser.add_argument(
        "--lookup",
        "-l",
        metavar="NAME",
        help="Find room by name and output room ID (for scripts)",
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["rooms"]
    if args.json:
        cli.append("--json")
    # Attached with "=", so a term that starts with "-" stays a value.
    if args.search is not None:
        cli.append(f"--search={args.search}")
    if args.lookup is not None:
        cli.append(f"--lookup={args.lookup}")
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env, json_errors=False)


if __name__ == "__main__":
    main()
