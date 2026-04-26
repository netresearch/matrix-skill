#!/usr/bin/env python3
"""Promote a user to power-level 100 in a room.

Calls ``POST /_synapse/admin/v1/rooms/{room_id}/make_room_admin``.
Synapse only lets this succeed while at least one existing room admin is
still a member.  If the original owner has left, the room is unrecoverable
through this tool.

Usage:
    synapse-make-admin.py <ROOM_ID> [USER_ID]

Falls back to ``$MATRIX_USER_ID`` when ``USER_ID`` is omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import admin_request, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("user_id", nargs="?", default=None)
    args = parser.parse_args()

    config = load_config()
    user_id = args.user_id or os.environ.get("MATRIX_USER_ID")
    if not user_id:
        print(
            "Error: USER_ID required (positional argument or $MATRIX_USER_ID).",
            file=sys.stderr,
        )
        return 2

    result = admin_request(
        config,
        "POST",
        f"/v1/rooms/{args.room_id}/make_room_admin",
        {"user_id": user_id},
    )
    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
