#!/usr/bin/env python3
"""Harden a room: link it into a space, restrict joins, enable encryption.

Multi-step operation:

1. Add the room to the target space (``m.space.child`` state event), unless
   already present.
2. Force-join the calling user.
3. If the user has no explicit power level, temporarily promote them to
   admin (PL 100).
4. If the room is currently public *and* its room-version supports
   restricted joins (>9), switch ``m.room.join_rules`` to ``restricted`` so
   only members of the parent space can join.
5. Enable Megolm encryption (``m.room.encryption``) if not already enabled.
6. Restore the user's original power level — runs in a ``finally`` block
   and on SIGINT/SIGTERM, so a crash or Ctrl-C does not leave the user
   with elevated permissions.

WARNING: enabling encryption is irreversible.  Restricted joins remove
discoverability for users outside the space.  The script therefore reads the
current state first, prints the steps it would take, and asks before the
first one changes anything.  ``--yes`` skips the question and is required to
run without a terminal.

Usage:
    synapse-migrate-room.py <ROOM_ID> [USER_ID] [SPACE_ID] [-y]

Falls back to ``$MATRIX_USER_ID`` / ``$MATRIX_SPACE_ID`` /
``default_space_id``.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    admin_request,
    bold,
    client_request,
    green,
    load_config,
    quote,
    red,
    yellow,
)

# Marks the one step in the pipeline that cannot be reversed.
IRREVERSIBLE = "IRREVERSIBLE"


def _state(config: dict, room_id: str) -> list[dict]:
    res = client_request(config, "GET", f"/rooms/{quote(room_id)}/state")
    if isinstance(res, list):
        return res
    return res.get("state", []) or []


def _put_state(
    config: dict,
    room_id: str,
    event_type: str,
    state_key: str,
    body: dict,
) -> dict:
    endpoint = f"/rooms/{quote(room_id)}/state/{quote(event_type)}/{quote(state_key)}"
    return client_request(config, "PUT", endpoint, body)


def _join(config: dict, room_id: str) -> dict:
    return client_request(config, "POST", f"/rooms/{quote(room_id)}/join", {})


def _restore_power_level(
    config: dict,
    room_id: str,
    user_id: str,
    pl_content: dict,
    previous_level: int | None,
) -> None:
    """Restore ``user_id``'s entry in the room's ``m.room.power_levels``.

    If ``previous_level`` is ``None`` the user originally had no explicit
    entry and ``users[user_id]`` is removed (so the user falls back to
    ``users_default``).  Otherwise the entry is set to ``previous_level``.

    Best-effort: errors are reported but never raised.
    """
    if not pl_content:
        return
    users = dict(pl_content.get("users") or {})
    if previous_level is None:
        if user_id not in users:
            return
        print(bold(yellow(f"⚠ Removing explicit PL entry for {user_id}")))
        users.pop(user_id, None)
    else:
        if users.get(user_id) == previous_level:
            return
        print(bold(yellow(f"⚠ Restoring {user_id} to power level {previous_level}")))
        users[user_id] = previous_level
    new_pl = dict(pl_content)
    new_pl["users"] = users
    res = _put_state(config, room_id, "m.room.power_levels", "", new_pl)
    if "error" in res:
        print(red(f"✗ Failed to restore power level: {res['error']}"), file=sys.stderr)
    else:
        print(bold(green("✓ Power levels restored")))


def plan_steps(
    room_id: str,
    space_id: str,
    user_id: str,
    already_child: bool,
    room_info: dict,
) -> list[tuple[bool, str, str]]:
    """The steps the pipeline is about to take, as ``(pending, text, note)``.

    Decided from state read before anything is written, so the operator sees
    the same decisions the pipeline will make.  ``pending`` is False for a
    step that is already satisfied and will be skipped.  ``note`` is empty
    unless the step needs a warning next to it.
    """
    join_rules = (room_info.get("join_rules") or "").lower()
    try:
        version = int(room_info.get("version") or 0)
    except (TypeError, ValueError):
        version = 0

    steps: list[tuple[bool, str, str]] = []

    if already_child:
        steps.append((False, f"Room is already a child of {space_id}", ""))
    else:
        steps.append((True, f"Add the room to {space_id}", "reversible"))

    steps.append(
        (
            True,
            f"Force-join {user_id}; raise to PL 100 if it is lower",
            "power level restored at the end",
        )
    )

    if join_rules != "public":
        steps.append((False, f"Join rules are already '{join_rules or 'unknown'}'", ""))
    elif version > 9:
        steps.append(
            (
                True,
                "Switch join rules public → restricted",
                "reversible, but hides the room from everyone outside the space",
            )
        )
    else:
        steps.append(
            (False, f"Room version {version} is too low for restricted joins", "")
        )

    if room_info.get("encryption"):
        steps.append((False, "Encryption is already enabled", ""))
    else:
        steps.append((True, "Enable Megolm encryption", IRREVERSIBLE))

    return steps


def print_plan(room_id: str, steps: list[tuple[bool, str, str]]) -> None:
    print(bold(f"Plan for {room_id}:"))
    for pending, text, note in steps:
        if not pending:
            print(f"  {green('·')} {text} — skipped")
        elif note == IRREVERSIBLE:
            print(f"  {bold(red('!'))} {text} — {bold(red('cannot be undone'))}")
        else:
            print(f"  {yellow('→')} {text}" + (f" — {note}" if note else ""))


def confirm(assume_yes: bool) -> int | None:
    """``None`` to proceed, otherwise the exit code to stop with.

    Mirrors ``synapse-deactivate-user.py``: a terminal is asked, a pipe is
    refused.  Refusing rather than defaulting to yes is the point — the
    pipeline's last step cannot be undone.
    """
    if assume_yes:
        return None
    if not sys.stdin.isatty():
        print(
            bold(red("Refusing to run non-interactively without --yes.")),
            file=sys.stderr,
        )
        return 2
    try:
        answer = input("Type 'YES' to continue: ").strip()
    except EOFError:
        answer = ""
    if answer != "YES":
        print(yellow("Aborted."))
        return 1
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("user_id", nargs="?", default=None)
    parser.add_argument("space_id", nargs="?", default=None)
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation.")
    args = parser.parse_args()

    config = load_config()
    user_id = args.user_id or os.environ.get("MATRIX_USER_ID")
    space_id = (
        args.space_id
        or os.environ.get("MATRIX_SPACE_ID")
        or config.get("default_space_id")
    )

    if not user_id:
        print("Error: USER_ID required.", file=sys.stderr)
        return 2
    if not space_id:
        print(
            "Error: SPACE_ID required (positional, $MATRIX_SPACE_ID, or "
            "'default_space_id' in config).",
            file=sys.stderr,
        )
        return 2

    from urllib.parse import urlparse

    via_host = urlparse(config["homeserver"]).hostname
    via = [via_host] if via_host else []

    # Read-only inspection first: the plan below has to describe the same
    # decisions the pipeline makes, and the operator has to see it while
    # nothing has changed yet.
    space_state = _state(config, space_id)
    already_child = any(
        s.get("type") == "m.space.child"
        and s.get("state_key") == args.room_id
        and (s.get("content") or {})
        for s in space_state
    )

    room_info = admin_request(config, "GET", f"/v1/rooms/{args.room_id}")
    if "error" in room_info:
        print(red(f"✗ {room_info['error']}"), file=sys.stderr)
        return 1

    print_plan(
        args.room_id,
        plan_steps(args.room_id, space_id, user_id, already_child, room_info),
    )
    stop = confirm(args.yes)
    if stop is not None:
        return stop

    # 1. Add to space if not already a child.
    if already_child:
        print(bold(green("✓ Room already in space")))
    else:
        print(bold(yellow("⚠ Adding room to space")))
        res = _put_state(
            config,
            space_id,
            "m.space.child",
            args.room_id,
            {"via": via, "suggested": False},
        )
        if "error" in res:
            print(red(f"✗ Failed to add to space: {res['error']}"), file=sys.stderr)
            return 1
        print(bold(green("✓ Room added to space")))

    # 2. Join.
    join_res = _join(config, args.room_id)
    if "error" in join_res:
        print(red(f"⚠ Join: {join_res['error']}"), file=sys.stderr)
    else:
        print(bold(green("✓ Joined")))

    # The room's own state needs membership, so it is read after the join.
    room_state = _state(config, args.room_id)

    pl_event = next(
        (s for s in room_state if s.get("type") == "m.room.power_levels"), None
    )
    pl_content = (pl_event or {}).get("content", {}) or {}
    users = dict(pl_content.get("users") or {})
    users_default = pl_content.get("users_default", 0)

    # `previous_level` retains its `None` if the user had no explicit entry.
    previous_level: int | None = users.get(user_id)
    had_explicit_entry = user_id in users
    promoted = False

    def _try_promote() -> bool:
        res = admin_request(
            config,
            "POST",
            f"/v1/rooms/{args.room_id}/make_room_admin",
            {"user_id": user_id},
        )
        if "error" in res:
            print(red(f"✗ Promote failed: {res['error']}"), file=sys.stderr)
            return False
        return True

    if not had_explicit_entry:
        print(
            bold(
                yellow(
                    f"⚠ {user_id} has no explicit power level (default {users_default}); "
                    f"will restore after operations"
                )
            )
        )
        promoted = _try_promote()
    elif previous_level == 100:
        print(bold(green("✓ User already has maximum power level")))
    else:
        print(
            bold(
                green(
                    f"✓ User has power level {previous_level}; will restore after operations"
                )
            )
        )
        promoted = _try_promote()

    if not promoted and not had_explicit_entry and previous_level is None:
        # We never managed to elevate; subsequent state writes will likely
        # fail.  Bail out cleanly without touching power levels.
        print(
            red("✗ Could not elevate user; skipping the rest of the pipeline."),
            file=sys.stderr,
        )
        return 1

    # Install a SIGINT/SIGTERM handler so Ctrl-C still restores the power
    # level before exiting.
    def _signal_handler(signum, _frame):
        if promoted:
            _restore_power_level(
                config, args.room_id, user_id, pl_content, previous_level
            )
        sys.exit(128 + signum)

    if promoted:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

    try:
        # 3. Restrict joins if currently public.
        join_rules = (room_info.get("join_rules") or "").lower()
        try:
            version = int(room_info.get("version") or 0)
        except (TypeError, ValueError):
            version = 0

        if join_rules == "public":
            if version > 9:
                print(bold(yellow("⚠ Setting join rules to restricted")))
                res = _put_state(
                    config,
                    args.room_id,
                    "m.room.join_rules",
                    "",
                    {
                        "join_rule": "restricted",
                        "allow": [{"type": "m.room_membership", "room_id": space_id}],
                    },
                )
                if "error" in res:
                    print(red(f"✗ Failed: {res['error']}"), file=sys.stderr)
                else:
                    print(bold(green("✓ Join rules set to restricted")))
            else:
                print(
                    bold(
                        red(
                            f"✗ Room version {version} is too low for restricted joins; "
                            "skipping"
                        )
                    )
                )
        else:
            print(bold(green("✓ Join rules already restricted (or not public)")))

        # 4. Encrypt if not already.
        if not room_info.get("encryption"):
            print(bold(yellow("⚠ Enabling encryption")))
            res = _put_state(
                config,
                args.room_id,
                "m.room.encryption",
                "",
                {"algorithm": "m.megolm.v1.aes-sha2"},
            )
            if "error" in res:
                print(red(f"✗ Failed: {res['error']}"), file=sys.stderr)
            else:
                print(bold(green("✓ Encryption enabled")))
        else:
            print(bold(green("✓ Encryption already enabled")))
    finally:
        # 5. Always restore the previous power level if we promoted the user,
        # even on exception.
        if promoted:
            _restore_power_level(
                config, args.room_id, user_id, pl_content, previous_level
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
