# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Shared part of the E2EE wrapper scripts.

Stdlib only. Each ``matrix-*-e2ee.py`` style script parses the flags it always
had, translates them into a matrix-e2ee-cli command line and hands over here:
find or download the binary, take over a pending matrix-nio device first, then
run the binary with this process's stdin, stdout and stderr, so prompts and the
verification emoji reach the terminal. Secrets travel in the environment of the
child, never on its command line.
"""

import os
import sys

from _lib import cli, cutover

# Commands, and flags before "--", that must not trigger the takeover of the
# nio device. Only the command (the first argument) and the flags count: a
# message or room called "logout" must not skip it.
NO_TAKEOVER_COMMANDS = {
    "migrate-nio",
    "logout",
    "help",
    "--help",
    "-h",
    "--version",
    "-V",
}
HELP_FLAGS = {"--help", "-h", "--version", "-V"}


class Unsupported(Exception):
    """An old flag the CLI has no equivalent for; the wrapper refuses it."""


def needs_takeover(args) -> bool:
    if not args or args[0] in NO_TAKEOVER_COMMANDS:
        return False
    flags = args[: args.index("--")] if "--" in args else args
    return not any(arg in HELP_FLAGS for arg in flags)


def run_cli(args, extra_env=None, env=None, choose=None) -> int:
    """Run matrix-e2ee-cli ARGS; its exit code (1 when it could not start).

    CHOOSE, when given, gets ARGS and the environment after the takeover and
    returns the arguments to run instead: what to run can depend on state the
    takeover creates (a session).
    """
    env = dict(os.environ if env is None else env)
    try:
        binary = cli.ensure_binary(env=env, log=cli.stderr_log)
        if needs_takeover(args):
            cutover.migrate_if_pending(binary, env=env)
        if choose is not None:
            args = choose(list(args), env)
        child_env = {**env, **extra_env} if extra_env else env
        return cli.run(binary, list(args), env=child_env)
    except (cli.CliError, cutover.CutoverError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def exit_with(args, extra_env=None, choose=None) -> None:
    sys.stdout.flush()
    sys.exit(run_cli(args, extra_env, choose=choose))


def refuse(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(2)


def secret_env(value, variable: str, allowed: bool, flag: str) -> dict:
    """A secret given on the wrapper's command line, for the child's environment.

    Refused without FLAG, as before: other local users can read argv in the
    process list. Passed on as VARIABLE, never as an argument.
    """
    if not value:
        return {}
    if not allowed:
        raise Unsupported(
            f"a secret on the command line is refused unless {flag} is given; "
            f"use the prompt or {variable} instead"
        )
    return {variable: value}
