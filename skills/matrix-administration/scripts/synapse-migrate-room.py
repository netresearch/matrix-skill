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
6. If we promoted the user in step 3, restore their original power level.

WARNING: enabling encryption is irreversible.  Restricted joins remove
discoverability for users outside the space.

Usage:
    synapse-migrate-room.py <ROOM_ID> [USER_ID] [SPACE_ID]

Falls back to ``$MATRIX_USER_ID`` / ``$MATRIX_SPACE_ID`` /
``default_space_id``.
"""

from __future__ import annotations

import argparse
import os
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
    endpoint = (
        f"/rooms/{quote(room_id)}/state/{quote(event_type)}/{quote(state_key)}"
    )
    return client_request(config, "PUT", endpoint, body)


def _join(config: dict, room_id: str) -> dict:
    return client_request(config, "POST", f"/rooms/{quote(room_id)}/join", {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("user_id", nargs="?", default=None)
    parser.add_argument("space_id", nargs="?", default=None)
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

    # 1. Add to space if not already a child.
    space_state = _state(config, space_id)
    already_child = any(
        s.get("type") == "m.space.child"
        and s.get("state_key") == args.room_id
        and (s.get("content") or {})
        for s in space_state
    )
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

    # Inspect target room.
    room_info = admin_request(config, "GET", f"/v1/rooms/{args.room_id}")
    if "error" in room_info:
        print(red(f"✗ {room_info['error']}"), file=sys.stderr)
        return 1
    room_state = _state(config, args.room_id)

    pl_event = next(
        (s for s in room_state if s.get("type") == "m.room.power_levels"), None
    )
    pl_content = (pl_event or {}).get("content", {}) or {}
    users = dict(pl_content.get("users") or {})
    users_default = pl_content.get("users_default", 0)

    previous_level = users.get(user_id)
    if previous_level is None:
        previous_level = users_default
        print(
            bold(
                yellow(
                    f"⚠ {user_id} has no explicit power level (default {users_default}); "
                    f"will restore after operations"
                )
            )
        )
        admin_request(
            config,
            "POST",
            f"/v1/rooms/{args.room_id}/make_room_admin",
            {"user_id": user_id},
        )
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
        admin_request(
            config,
            "POST",
            f"/v1/rooms/{args.room_id}/make_room_admin",
            {"user_id": user_id},
        )

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
                    "allow": [
                        {"type": "m.room_membership", "room_id": space_id}
                    ],
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

    # 5. Restore previous power level if we changed it.
    if pl_content and users.get(user_id) != 100:
        print(bold(yellow(f"⚠ Restoring {user_id} to power level {previous_level}")))
        new_users = dict(users)
        new_users[user_id] = previous_level
        new_pl = dict(pl_content)
        new_pl["users"] = new_users
        res = _put_state(config, args.room_id, "m.room.power_levels", "", new_pl)
        if "error" in res:
            print(red(f"✗ Failed: {res['error']}"), file=sys.stderr)
        else:
            print(bold(green("✓ Power levels restored")))

    return 0


if __name__ == "__main__":
    sys.exit(main())
