#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Set up this skill's own E2EE device, or show its state.

Runs `matrix-e2ee-cli login` (a new device "Matrix Skill E2EE (Rust)") or
`matrix-e2ee-cli status`. A matrix-nio device of an older version of this
skill is taken over first instead (see _lib/cutover.py), so it keeps its
verification and room keys.

Usage:
    matrix-e2ee-setup.py                         # prompts for the password
    MATRIX_PASSWORD=... matrix-e2ee-setup.py     # non-interactive
    matrix-e2ee-setup.py --allow-secret-argument PASSWORD
    matrix-e2ee-setup.py --status [--json]

--logout and --purge-all are refused: the old flag only deleted local files,
while `matrix-e2ee-cli logout` logs the device out on the server. Run
`matrix-e2ee-cli.py logout` when that is what you want. --json without
--status is refused (login has no JSON output). --debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse, secret_env

ALLOW_FLAG = "--allow-secret-argument"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up the E2EE device of the Matrix skill"
    )
    parser.add_argument(
        "password", nargs="?", help=f"Account password; refused unless {ALLOW_FLAG}"
    )
    parser.add_argument(ALLOW_FLAG, dest="allow_secret_argument", action="store_true")
    parser.add_argument(
        "--status", action="store_true", help="Show the E2EE device state"
    )
    parser.add_argument(
        "--logout", action="store_true", help="Refused (see the docstring)"
    )
    parser.add_argument(
        "--purge-all", action="store_true", help="Refused (see the docstring)"
    )
    parser.add_argument(
        "--json", action="store_true", help="With --status: JSON output"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.logout or args.purge_all:
        raise Unsupported(
            "--logout and --purge-all are not supported any more. The old flag deleted local "
            "files only; `matrix-e2ee-cli.py logout` also logs the device out on the server, "
            "which ends it for good. Never run it to retire the copy an older version of this "
            "skill left in ~/.local/share/matrix-skill/store: delete that directory yourself."
        )
    if args.status:
        return (["status", "--json"] if args.json else ["status"]), None
    if args.json:
        raise Unsupported("--json is only supported with --status")
    extra = secret_env(
        args.password, "MATRIX_PASSWORD", args.allow_secret_argument, ALLOW_FLAG
    )
    return ["login"], extra


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env)


if __name__ == "__main__":
    main()
