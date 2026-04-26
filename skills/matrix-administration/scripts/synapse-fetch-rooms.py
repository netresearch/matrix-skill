#!/usr/bin/env python3
"""Snapshot every visible room on a Synapse homeserver.

Pages through ``GET /_synapse/admin/v1/rooms`` and, for each room, fetches
its full state via ``/v1/rooms/{room_id}/state``.  Writes the result as a
JSON list of ``{"room": …, "states": […]}`` entries — the format consumed
by the other scripts (rating, graph, member listings).

Apply an optional server-suffix filter via ``--server`` (e.g.
``--server :example.com``) or the ``room_filter`` config field.  Without a
filter every visible room is included.

Usage:
    synapse-fetch-rooms.py [--output rooms.json] [--server :example.com]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import admin_request, load_config, quote


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "-o", "--output", default="rooms.json", help="Output path (default rooms.json)"
    )
    parser.add_argument(
        "--server",
        default=None,
        help="Optional server suffix to filter on (e.g. ':example.com'). "
        "Defaults to the 'room_filter' config field.",
    )
    args = parser.parse_args()

    config = load_config()
    suffix = args.server if args.server is not None else config.get("room_filter", "")

    from_token: int | str = 0
    rooms: list[dict] = []

    while True:
        result = admin_request(
            config, "GET", f"/v1/rooms?from={quote(str(from_token))}&sort"
        )
        if "error" in result:
            print(f"Error fetching rooms: {result['error']}", file=sys.stderr)
            return 1

        page = result.get("rooms", []) or []
        if suffix:
            page = [r for r in page if r.get("room_id", "").endswith(suffix)]

        for room in page:
            state_res = admin_request(
                config, "GET", f"/v1/rooms/{room['room_id']}/state"
            )
            if "error" in state_res:
                print(
                    f"Warning: failed to fetch state for {room['room_id']}: "
                    f"{state_res['error']}",
                    file=sys.stderr,
                )
                continue
            states = sorted(
                state_res.get("state", []) or [],
                key=lambda s: s.get("origin_server_ts", 0),
            )
            rooms.append({"room": room, "states": states})

        next_batch = result.get("next_batch")
        if next_batch is None:
            break
        from_token = next_batch

    with open(args.output, "w") as f:
        json.dump(rooms, f, indent=2)

    print(f"Wrote {len(rooms)} rooms to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
