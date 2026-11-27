#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Verify this device with one of your own devices (SAS emoji).

Runs `matrix-e2ee-cli verify`. The CLI needs a terminal on stdin and stderr
for --request and --listen; without one, use the hand-over flow of
`matrix-e2ee-cli.py verify --hand-over` (see references/e2ee-guide.md).

Usage:
    matrix-e2ee-verify.py --request DEVICE [--timeout S]
    matrix-e2ee-verify.py --listen [--timeout S]
    matrix-e2ee-verify.py --list

Not supported any more: running without --request, --listen or --list (it
picked a device itself) and --accept-from (the CLI verifies devices of your
own account only). The default timeout is the CLI's, 180 s (was 120 s).
--debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify this E2EE device (SAS emoji)")
    parser.add_argument(
        "--request", metavar="DEVICE", help="Verify with this device of your own"
    )
    parser.add_argument("--list", action="store_true", help="List your devices")
    parser.add_argument(
        "--listen", action="store_true", help="Wait for a request from another device"
    )
    parser.add_argument(
        "--accept-from", metavar="USER_ID", action="append", default=[], help="Refused"
    )
    parser.add_argument(
        "--timeout", type=int, help="Give up after this many seconds (default: 180)"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.accept_from:
        raise Unsupported(
            "--accept-from is not supported any more: matrix-e2ee-cli verifies devices of "
            "your own account only"
        )
    modes = [flag for flag in ("request", "listen", "list") if getattr(args, flag)]
    if len(modes) != 1:
        raise Unsupported(
            "give exactly one of --request DEVICE, --listen or --list; the device to "
            "verify is no longer picked automatically (--list shows the ids)"
        )
    cli = ["verify"]
    if args.request:
        cli += ["--request", args.request]
    elif args.listen:
        cli.append("--listen")
    else:
        cli.append("--list")
    if args.timeout is not None:
        cli += ["--timeout", str(args.timeout)]
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
