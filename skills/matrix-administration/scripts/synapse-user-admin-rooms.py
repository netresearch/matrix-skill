#!/usr/bin/env python3
"""List rooms where the given user is a power-level-100 admin.

Reads the local ``rooms.json`` snapshot (produced by
``synapse-fetch-rooms.py``) and counts how many *other* admins are present
in each room — useful for spotting single-admin / single-point-of-failure
rooms.

Usage:
    synapse-user-admin-rooms.py [USER_ID] [--input rooms.json]

Falls back to ``$MATRIX_USER_ID``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import bold, condense, gray, green, red, yellow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("user_id", nargs="?", default=None)
    parser.add_argument("-i", "--input", default="rooms.json")
    args = parser.parse_args()

    user_id = args.user_id or os.environ.get("MATRIX_USER_ID")
    if not user_id:
        print("Error: USER_ID required.", file=sys.stderr)
        return 2

    with open(args.input) as f:
        data = json.load(f)
    rooms = condense(data)

    matches = []
    for r in rooms.values():
        if r.is_replaced:
            continue
        if r.permissions.get(user_id, 0) == 100:
            others = [
                uid
                for uid, lvl in r.permissions.items()
                if uid != user_id and lvl == 100
            ]
            matches.append((r, others))

    matches.sort(key=lambda pair: pair[0].name.lower())

    if not matches:
        print(gray(f"{user_id} is not an admin in any room"))
        return 0

    max_name = max(len(r.name) for r, _ in matches)
    for r, others in matches:
        # Pad the plain name first; colour codes don't count toward width.
        padding = " " * (max_name - len(r.name))
        name = bold(yellow(r.name)) + padding
        if others:
            label = green(f"({len(others)} other admins)")
        else:
            label = red("(no other admins)")
        print(f"{name}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
