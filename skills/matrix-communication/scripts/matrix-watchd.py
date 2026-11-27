#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Watch daemon: holds the E2EE store, logs the rooms in "watch_rooms".

Runs `matrix-e2ee-cli watch-daemon` (Linux and macOS). While it runs, send,
react, redact and edit of the CLI go through it.

Usage:
    matrix-watchd.py --start | --stop | --status | --foreground
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Matrix watch daemon")
    group = parser.add_mutually_exclusive_group(required=True)
    for flag, text in (
        ("start", "Start in the background"),
        ("stop", "Stop a running daemon"),
        ("status", "Ask a running daemon"),
        ("foreground", "Run in this terminal"),
    ):
        group.add_argument(f"--{flag}", action="store_true", help=text)
    return parser


def translate(args):
    flag = next(
        f for f in ("start", "stop", "status", "foreground") if getattr(args, f)
    )
    return ["watch-daemon", f"--{flag}"], None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env)


if __name__ == "__main__":
    main()
