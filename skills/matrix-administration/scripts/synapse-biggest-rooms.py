#!/usr/bin/env python3
"""Print the largest rooms on the homeserver by Synapse-estimated DB size.

Calls ``GET /_synapse/admin/v1/statistics/database/rooms`` and looks up the
display name for each result.  Limit defaults to 10.

Usage:
    synapse-biggest-rooms.py [--limit 10]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import admin_request, load_config, pretty_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-n", "--limit", type=int, default=10)
    args = parser.parse_args()

    config = load_config()
    result = admin_request(config, "GET", "/v1/statistics/database/rooms")
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    rooms = result.get("rooms", []) or []
    rooms.sort(key=lambda r: r.get("estimated_size", 0), reverse=True)
    rooms = rooms[: args.limit]

    rows = []
    for r in rooms:
        info = admin_request(config, "GET", f"/v1/rooms/{r['room_id']}")
        name = info.get("name") if isinstance(info, dict) else None
        rows.append(
            {
                "room_id": r["room_id"],
                "name": name,
                "size": pretty_bytes(r.get("estimated_size", 0)),
            }
        )

    width_id = max((len(row["room_id"]) for row in rows), default=8)
    width_size = max((len(row["size"]) for row in rows), default=4)
    print(f"{'room_id'.ljust(width_id)}  {'size'.rjust(width_size)}  name")
    for row in rows:
        name = row["name"] or "-"
        print(
            f"{row['room_id'].ljust(width_id)}  {row['size'].rjust(width_size)}  {name}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
