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
    matrix-e2ee-setup.py --force                 # replace a dead or foreign device

With a session already in place (also right after the takeover of a
matrix-nio device) it does not log in again: it says so, shows
`matrix-e2ee-cli status` and exits with its code. --force runs
`matrix-e2ee-cli login --force`, which replaces the local session with a new
device; the old device stays on the server (remove it in Element).

--logout and --purge-all are refused: the old flag only deleted local files,
while `matrix-e2ee-cli logout` logs the device out on the server. Run
`matrix-e2ee-cli.py logout` when that is what you want. --json without
--status is refused (login has no JSON output). --debug is accepted and ignored.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.cutover import CutoverError, cli_session_path, nio_store_path
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing session with a new device (dead or foreign token)",
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.logout or args.purge_all:
        try:
            store = str(nio_store_path(os.environ))
        except CutoverError:
            store = "the matrix-skill/store directory of your data directory"
        raise Unsupported(
            "--logout and --purge-all are not supported any more. The old flag deleted local "
            "files only; `matrix-e2ee-cli.py logout` also logs the device out on the server, "
            "which ends it for good. Do not use it for the copy an older version of this "
            f"skill left in {store}. Keep that store until the takeover has succeeded (the "
            "first E2EE command makes a backup and runs it) and the new device works; "
            "only then remove it, if you want to."
        )
    if args.status and args.force:
        raise Unsupported("--force replaces the device; it does not go with --status")
    if args.status:
        return (["status", "--json"] if args.json else ["status"]), None
    if args.json:
        raise Unsupported("--json is only supported with --status")
    extra = secret_env(
        args.password, "MATRIX_PASSWORD", args.allow_secret_argument, ALLOW_FLAG
    )
    return (["login", "--force"] if args.force else ["login"]), extra


def keep_existing_session(cli_args, env):
    """Run status instead of a login that would refuse an existing session.

    Decided after the takeover, which may just have created the session.
    """
    if cli_args != ["login"]:
        return cli_args
    try:
        exists = cli_session_path(env).exists()
    except CutoverError:
        return cli_args
    if not exists:
        return cli_args
    print(
        "E2EE already set up. To replace a dead or foreign device, run "
        "matrix-e2ee-setup.py --force (never matrix-e2ee-cli.py logout for that: it "
        "ends the device on the server).",
        flush=True,
    )
    return ["status"]


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env, choose=keep_existing_session)


if __name__ == "__main__":
    main()
