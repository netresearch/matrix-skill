#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""React to a Matrix message: add, remove, swap or list your own reactions.

Runs `matrix-e2ee-cli react` (see _lib/cli.py for how the binary is found).

Usage:
    matrix-react.py ROOM EVENT_ID EMOJI [EMOJI ...] [--replace OLD ...]
    matrix-react.py ROOM EVENT_ID EMOJI [EMOJI ...] --remove
    matrix-react.py ROOM EVENT_ID --list

Several EMOJI are set in one call, in the order given. --replace is a status
swap: set EMOJI, then remove this account's own reactions with any of OLD on
the same event (after the last EMOJI). The account's own reactions are looked
up on the server, so no reaction id is needed. Prints "Reacted with … to …" and
"Event ID: $…" per EMOJI (--quiet: the ids alone, --json: JSON); --list prints
"EMOJI<TAB>reaction event id" per own reaction.

Reactions are sent unencrypted, also in an encrypted room, so
--trust-unverified-devices shares no key; it is accepted for old callers.
--debug is accepted and ignored.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib.rooms import normalize_room_input
from _lib.utils import clean_message
from _lib.wrapper import Unsupported, exit_with, json_error, refuse, room_chooser

APPLIED = "Applied before the error: "
EVENT_ID = r"\$[^\s(),]+"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="React to a Matrix message with an emoji"
    )
    parser.add_argument("room", help="Room ID, alias, name or matrix.to link")
    parser.add_argument("event_id", help="Event ID of the message to react to")
    parser.add_argument("emoji", nargs="*", help="Reaction key(s); not with --list")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--replace",
        nargs="+",
        default=[],
        metavar="OLD",
        help="Status swap: remove own OLD after setting EMOJI",
    )
    mode.add_argument(
        "--remove",
        action="store_true",
        help="Remove own EMOJI reactions instead of adding them",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="List own reactions on the event; changes nothing",
    )
    parser.add_argument(
        "--trust-unverified-devices",
        action="store_true",
        help="Accepted for old callers; no effect (reactions are sent unencrypted)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Print only the reaction event ids"
    )
    parser.add_argument("--debug", action="store_true", help="Ignored")
    return parser


def translate(args):
    if args.list and args.emoji:
        raise Unsupported("--list takes no EMOJI")
    if not args.list and not args.emoji:
        raise Unsupported("EMOJI is required unless --list is given")
    cli = ["react"]
    for flag in ("remove", "list", "trust_unverified_devices", "json", "quiet"):
        if getattr(args, flag):
            cli.append("--" + flag.replace("_", "-"))
    if args.replace:
        cli += ["--replace", *args.replace]
    cli += [
        "--",
        normalize_room_input(clean_message(args.room)),
        args.event_id,
        *args.emoji,
    ]
    return cli, None


def _applied(line: str, keys: list):
    """How many of KEYS the "Applied before the error" line lists, or None.

    The CLI joins the keys with spaces, so a key with a space in it cannot be
    split off the line; matching the line against the keys this script sent
    tells where each one ends.
    """
    text = line.removeprefix(APPLIED)
    matches = [n for n in range(1, len(keys) + 1) if " ".join(keys[:n]) == text]
    return matches[0] if len(matches) == 1 else None


def _removal(error: str, current: str, dropped: list):
    """(event_id, removed) from react.rs's "could not remove" error, or None.

    The text is "could not remove KEY (ID)[ (already done: set KEY (ID),
    removed KEY (ID), ...)]: CAUSE". Only keys this call could have set or
    removed are matched, and only a parse that reproduces the text exactly
    and is the same with the longest or the shortest key tried first counts.
    """
    if not error.startswith("could not remove ") or not dropped:
        return None
    parses = set()
    for order in (False, True):
        names = sorted(set(dropped), key=len, reverse=not order)
        key = "|".join(re.escape(k) for k in names)
        removed = rf"removed (?:{key}) \({EVENT_ID}\)"
        listing = rf"{removed}(?:, {removed})*"
        done = (
            rf"set {re.escape(current)} \((?P<set>{EVENT_ID})\)(?:, (?P<after>{listing}))?"
            rf"|(?P<only>{listing})"
        )
        pattern = (
            rf"could not remove (?:{key}) \({EVENT_ID}\)"
            rf"(?: \(already done: (?:{done})\))?: .+"
        )
        match = re.fullmatch(pattern, error, re.DOTALL)
        if not match:
            continue
        event_id = match.group("set")
        listed = match.group("after") or match.group("only") or ""
        keys = tuple(
            re.findall(rf"removed ({key}) \({EVENT_ID}\)", listed) if listed else ()
        )
        parses.add((event_id, keys))
    if len(parses) != 1:
        return None
    event_id, keys = parses.pop()
    return event_id, list(keys)


def failure_json(stderr: str, keys: list, replace: list, remove: bool) -> dict:
    """The old --json failure object from matrix-e2ee-cli react's stderr.

    As version 4 printed it: "error", "applied" (the keys set before the
    failing one) and, when a swap or removal failed while removing,
    "event_id" (the failing key's own reaction, or null) and "removed". What
    cannot be read without guessing is left out, and the stderr lines
    involved are passed on whole in "unparsed".
    """
    payload = json_error(stderr)
    unparsed = []
    applied = 0
    for line in stderr.splitlines():
        if line.startswith(APPLIED):
            count = _applied(line, keys)
            if count is None:
                unparsed.append(line)
            else:
                applied = count
                payload["applied"] = keys[:count]
    current = keys[applied] if applied < len(keys) else None
    error = payload["error"]
    if current is not None and error.startswith("could not remove "):
        dropped = [current] if remove else [k for k in replace if k not in keys]
        parsed = _removal(error, current, dropped)
        if parsed is None:
            unparsed.append(f"error: {error}")
        else:
            payload["event_id"], payload["removed"] = parsed
    if unparsed:
        payload["unparsed"] = unparsed
    return payload


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        cli_args, extra_env = translate(args)
    except Unsupported as exc:
        refuse(str(exc))
    exit_with(
        cli_args,
        extra_env,
        choose=room_chooser(cli_args[cli_args.index("--") + 1], write=True),
        json_errors=(
            (lambda stderr: failure_json(stderr, args.emoji, args.replace, args.remove))
            if args.json
            else False
        ),
    )


if __name__ == "__main__":
    main()
