# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Resolve a room shorthand the way the scripts did before matrix-e2ee-cli.

Stdlib only. matrix-e2ee-cli reads ROOM as a room ID (``!…``), a full alias
(``#name:server``) or, for anything else, an exact display name. The scripts
of version 4 resolved a shorthand differently: an alias without its server
part (``ops`` or ``#ops`` for ``#ops:example.org``) came before a display
name, and a single partial match counted too. Passed on unchanged, ``ops``
can therefore reach a different room than before, and both succeed.

So a shorthand is resolved here to a room ID, in the order of
``find_room_in_nio_client``, which the E2EE scripts of version 4 used: alias
without server, then a single exact display name (or, for a room named after
its members, a member's user ID), then a single partial match. Only the ID
reaches the CLI. Two deviations, both refusals: several rooms with the same
alias name are refused instead of taking the first, and a command that writes
(send, edit, react, redact, invite, power-level --set) takes no partial match. Room IDs and full aliases
pass unchanged, without running anything. The lookup takes the joined rooms
from ``matrix-e2ee-cli rooms --json`` (the CLI's own session and store, or
the watch daemon while it runs), so it reads no token itself. No match,
several matches, a room whose members could not be read, or a listing that
fails stop the command: it never falls back to the CLI's own, different
choice.
"""

import json
import sys

from _lib import cli, cutover
from _lib.rooms import room_matches

# rooms.rs prints this for a room named after its members whose members it
# could not read; that room then goes by its room id and could not match.
MEMBERS_WARNING = "warning: cannot read the members of "


class RoomLookupError(Exception):
    """The shorthand matched no room, several rooms, or could not be looked up."""


def is_shorthand(room: str) -> bool:
    """Not a room ID and not an alias with its server part."""
    return not room.startswith("!") and not (room.startswith("#") and ":" in room)


def _alias_localpart(room: dict) -> str:
    return (room.get("alias") or "").split(":")[0].lstrip("#").lower()


def _listed(rooms) -> str:
    return ", ".join(
        f"{r.get('name')} ({r.get('alias') or r['room_id']})" for r in rooms
    )


def choose(room: str, term: str, rooms: list, write: bool) -> str:
    """The room ID TERM names among ROOMS, in the order of version 4."""
    lowered = term.lower()
    for tier, matches in (
        (
            "alias",
            [r for r in rooms if r.get("alias") and _alias_localpart(r) == lowered],
        ),
        ("name", [r for r in rooms if room_matches(r, lowered, exact=True)]),
    ):
        if len(matches) == 1:
            return matches[0]["room_id"]
        if len(matches) > 1:
            raise RoomLookupError(
                f"{room!r} matches several rooms by {tier}: {_listed(matches)}; pass "
                "the room ID or full alias"
            )
    partial = [r for r in rooms if room_matches(r, lowered)]
    if len(partial) > 1:
        raise RoomLookupError(
            f"{room!r} matches several rooms: {_listed(partial)}; pass the room ID or "
            "full alias"
        )
    if partial and write:
        raise RoomLookupError(
            f"{room!r} is only part of the name of {_listed(partial)}; a command that "
            "writes needs the exact name, the room ID or the full alias"
        )
    if partial:
        return partial[0]["room_id"]
    raise RoomLookupError(
        f"no joined room matches {room!r}; matrix-rooms.py lists them"
    )


def cli_rooms(env) -> list:
    """The joined rooms as ``matrix-e2ee-cli rooms --json`` lists them.

    Its stdout never reaches this process's stdout. Raises ValueError when
    the listing fails, prints no list of rooms, or warns that the members of
    a room could not be read; other stderr lines are passed on.
    """
    binary = cli.ensure_binary(env=env, log=cli.stderr_log)
    result = cli.run_captured(binary, ["rooms", "--json"], env=env)
    unreadable, errors = [], []
    for line in result.stderr.splitlines():
        if line.startswith(MEMBERS_WARNING):
            unreadable.append(line.removeprefix("warning: "))
        elif line.startswith("error: "):
            errors.append(line.removeprefix("error: "))
        elif line.strip():
            print(line, file=sys.stderr)
    if result.returncode != 0:
        detail = "; ".join(errors) or f"exit code {result.returncode}"
        raise ValueError(f"matrix-e2ee-cli rooms failed: {detail}")
    if unreadable:
        raise ValueError("; ".join(unreadable))
    try:
        rooms = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError(f"matrix-e2ee-cli rooms printed no JSON: {exc}") from exc
    if not isinstance(rooms, list) or not all(
        isinstance(r, dict)
        and isinstance(r.get("room_id"), str)
        and isinstance(r.get("name"), str)
        for r in rooms
    ):
        raise ValueError("matrix-e2ee-cli rooms printed no list of rooms")
    return rooms


def resolve(room: str, env, lister=cli_rooms, write=False) -> str:
    """The room ID the old scripts chose for ROOM; ROOM itself when it is exact.

    Without a session there is nothing to look up with, and the CLI, which
    needs the session too, reports that itself. With WRITE (send, edit,
    react, redact, invite, power-level --set) only an exact alias or an exact name counts: a room
    name is chosen by whoever named the room, and a partial match would
    let such a name decide where a message goes.
    """
    if not is_shorthand(room):
        return room
    # matrix-send-e2ee.py and friends looked "#ops" up as the name "ops".
    term = room.removeprefix("#")
    try:
        if not cutover.cli_session_path(env).exists():
            return room
    except cutover.CutoverError:
        return room
    try:
        rooms = lister(env)
    except (OSError, ValueError) as exc:  # a failed or unreadable listing
        raise RoomLookupError(
            f"cannot list the joined rooms to find {room!r} ({exc}); pass its room ID "
            "(!…) or full alias (#name:server)"
        ) from exc
    return choose(room, term, rooms, write)
