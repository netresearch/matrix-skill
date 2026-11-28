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

import json
import os
import sys

from _lib import cli, cutover, room_lookup

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
# Commands that never open the store: watch reads the daemon's logs, and a
# daemon control request only talks to the socket.
NO_STORE = {"watch"}
NO_STORE_DAEMON_FLAGS = {"--status", "--stop"}


class Unsupported(Exception):
    """An old flag the CLI has no equivalent for; the wrapper refuses it."""


def needs_takeover(args) -> bool:
    if not args or args[0] in NO_TAKEOVER_COMMANDS or args[0] in NO_STORE:
        return False
    if args[0] == "watch-daemon" and NO_STORE_DAEMON_FLAGS & set(args[1:]):
        return False
    flags = args[: args.index("--")] if "--" in args else args
    return not any(arg in HELP_FLAGS for arg in flags)


def is_explicit_migration(args) -> bool:
    """``migrate-nio`` itself, not its help."""
    if not args or args[0] != "migrate-nio":
        return False
    flags = args[: args.index("--")] if "--" in args else args
    return not any(arg in HELP_FLAGS for arg in flags)


def json_error(stderr: str) -> dict:
    """The old scripts' --json error object from the CLI's stderr.

    The CLI ends a failure with one "error: ..." line. matrix-react.py reads
    its other lines itself (see its failure_json), because only it knows the
    reaction keys and can tell where one ends.
    """
    payload = {"error": ""}
    for line in stderr.splitlines():
        if line.startswith("error: "):
            payload["error"] = line.removeprefix("error: ")
    if not payload["error"]:
        payload["error"] = (
            stderr.strip().splitlines()[-1] if stderr.strip() else "failed"
        )
    return payload


def run_cli(args, extra_env=None, env=None, choose=None, json_errors=False) -> int:
    """Run matrix-e2ee-cli ARGS; its exit code (1 when it could not start).

    CHOOSE, when given, gets ARGS and the environment after the takeover and
    returns the arguments to run instead: what to run can depend on state the
    takeover creates (a session). With JSON_ERRORS, a failure that printed
    nothing on stdout prints the old scripts' {"error": ...} object there;
    JSON_ERRORS may be a function that builds that object from the stderr.
    """
    env = dict(os.environ if env is None else env)
    try:
        binary = cli.ensure_binary(env=env, log=cli.stderr_log)
        if is_explicit_migration(args):
            return cutover.explicit_migrate(binary, list(args), env=env)
        cutover.settle(env)
        if needs_takeover(args):
            try:
                cutover.migrate_if_pending(binary, env=env)
            except OSError as exc:
                # A lock file, the backup or the marker could not be used:
                # the command stays blocked, with a message instead of a trace.
                raise cutover.CutoverError(
                    f"the takeover of the matrix-nio device failed: {exc}"
                ) from exc
        if choose is not None:
            args = choose(list(args), env)
        child_env = {**env, **extra_env} if extra_env else env
        if not json_errors:
            return cli.run(binary, list(args), env=child_env)
        result = cli.run_captured(binary, list(args), env=child_env)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0 and not result.stdout.strip():
            build = json_errors if callable(json_errors) else json_error
            print(json.dumps(build(result.stderr)))
        return result.returncode
    except Unsupported as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except room_lookup.Interrupted:
        return 130  # as cli.run on Ctrl-C: no message
    except (cli.CliError, cutover.CutoverError, room_lookup.RoomLookupError) as exc:
        if json_errors:
            print(json.dumps({"error": str(exc)}))
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def exit_with(args, extra_env=None, choose=None, json_errors=False) -> None:
    sys.stdout.flush()
    sys.exit(run_cli(args, extra_env, choose=choose, json_errors=json_errors))


def room_chooser(room: str, write=False):
    """A CHOOSE for run_cli that puts the room the old scripts chose in place.

    ROOM stands right after "--", except for send, whose optional ROOM stands
    right before it.
    """

    def choose(args, env):
        resolved = room_lookup.resolve(room, env, write=write)
        separator = args.index("--")
        index = separator - 1 if args[0] == "send" else separator + 1
        if args[0] == "send" and resolved.startswith("-"):
            # Before "--" it would be read as a flag; resolve() returns room
            # IDs and full aliases, so this only guards against a change.
            raise Unsupported(f"room {resolved!r} starts with '-'; that is no room")
        args[index] = resolved
        return args

    return choose


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
