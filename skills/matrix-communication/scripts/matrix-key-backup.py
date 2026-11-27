#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Restore room keys from the server-side key backup.

Runs `matrix-e2ee-cli backup-restore` (with --import-keys) or
`matrix-e2ee-cli status` (with --status).

Usage:
    matrix-key-backup.py --import-keys                  # prompts for the key or passphrase
    matrix-key-backup.py --recovery-key --import-keys   # the same
    matrix-key-backup.py --passphrase --import-keys     # the same
    matrix-key-backup.py --status

The key comes from MATRIX_RECOVERY_KEY, MATRIX_RECOVERY_PASSPHRASE or the
prompt; a value on the command line only with --allow-secret-argument, and it
is passed on in the environment. Every run needs the key: the CLI keeps no
backup key of the old kind. Without --import-keys or --status nothing is
done: the CLI has no display-only mode; with both, --status wins and nothing
is imported. The room keys come for the rooms the account is joined to only;
after rejoining a room, run --import-keys again for its history.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.wrapper import Unsupported, exit_with, refuse, secret_env

ALLOW_FLAG = "--allow-secret-argument"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Matrix key backup")
    parser.add_argument(
        "--recovery-key",
        nargs="?",
        const="",
        help="Recovery key (prompt or MATRIX_RECOVERY_KEY)",
    )
    parser.add_argument(
        "--passphrase",
        nargs="?",
        const="",
        help="Passphrase (prompt or MATRIX_RECOVERY_PASSPHRASE)",
    )
    parser.add_argument(ALLOW_FLAG, dest="allow_secret_argument", action="store_true")
    parser.add_argument(
        "--status", action="store_true", help="Show the key-backup state"
    )
    parser.add_argument(
        "--import-keys", action="store_true", help="Import the room keys"
    )
    return parser


def translate(args):
    extra = {}
    extra.update(
        secret_env(
            args.recovery_key,
            "MATRIX_RECOVERY_KEY",
            args.allow_secret_argument,
            ALLOW_FLAG,
        )
    )
    extra.update(
        secret_env(
            args.passphrase,
            "MATRIX_RECOVERY_PASSPHRASE",
            args.allow_secret_argument,
            ALLOW_FLAG,
        )
    )
    if args.status:
        # Read-only, as before: with --import-keys too, the old script only
        # reported the backup state.
        return ["status"], None
    if args.import_keys:
        return ["backup-restore"], extra or None
    raise Unsupported(
        "give --import-keys (restore the room keys) or --status; matrix-e2ee-cli has no "
        "mode that only displays the keys"
    )


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(cli_args, extra_env)


if __name__ == "__main__":
    main()
