#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve a Matrix room alias to room ID.

Runs `matrix-e2ee-cli resolve` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-resolve.py ALIAS [--json]
    matrix-resolve.py --help

Arguments:
    ALIAS       Room alias (e.g., #myroom:matrix.org)

Options:
    --json      Output as JSON
    --help      Show this help

--debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve a Matrix room alias to room ID"
    )
    parser.add_argument("alias", help="Room alias (e.g., #myroom:matrix.org)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    cli = ["resolve"]
    if args.json:
        cli.append("--json")
    cli += ["--", args.alias]
    return cli, None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if not args.alias.startswith("#"):
        # Checked before anything runs, as in version 5.0.0: no takeover, no
        # session, no CLI.
        print("Error: Alias must start with #", file=sys.stderr)
        sys.exit(1)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env, json_errors=args.json)


if __name__ == "__main__":
    main()
