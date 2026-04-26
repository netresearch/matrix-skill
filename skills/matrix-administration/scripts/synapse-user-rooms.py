#!/usr/bin/env python3
"""List every room where the given user is a member.

Reads the local ``rooms.json`` snapshot.  For each room, prints version
and the timestamp of the user's join event.  Replaced (tombstoned) rooms
are dimmed.

Usage:
    synapse-user-rooms.py [USER_ID] [--input rooms.json]

Falls back to ``$MATRIX_USER_ID``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import bold, condense, gray, yellow


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
        joined = r.members.get(user_id)
        if joined is None:
            continue
        matches.append((r, joined))

    matches.sort(key=lambda pair: pair[0].name.lower())

    if not matches:
        print(gray(f"{user_id} is not a member of any indexed room"))
        return 0

    for r, joined in matches:
        color = gray if r.is_replaced else yellow
        name = bold(color(r.name))
        info = gray(f"(v{r.version}, joined {joined.isoformat()})")
        print(f"{name} {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
