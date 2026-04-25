#!/usr/bin/env python3
"""Search a single room for unencrypted messages by a user.

Calls ``POST /_matrix/client/v3/search``.  Only **unencrypted** messages
are searchable — end-to-end encrypted rooms return nothing.  The token
holder must be a member of the room.

Usage:
    synapse-search.py <ROOM_ID> <USER_ID> <TERM…>
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import client_request, gray, load_config, quote


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("user_id")
    parser.add_argument("terms", nargs="+")
    args = parser.parse_args()

    config = load_config()
    term = " ".join(args.terms)

    next_batch: str | None = None
    messages: list[dict] = []

    while True:
        endpoint = "/search"
        if next_batch is not None:
            endpoint += f"?next_batch={quote(next_batch)}"
        body = {
            "search_categories": {
                "room_events": {
                    "groupings": {"group_by": [{"key": "room_id"}]},
                    "filter": {
                        "limit": 1000,
                        "senders": [args.user_id],
                        "rooms": [args.room_id],
                    },
                    "keys": ["content.body"],
                    "order_by": "recent",
                    "search_term": term,
                }
            }
        }

        result = client_request(config, "POST", endpoint, body)
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1

        events = (
            result.get("search_categories", {}).get("room_events", {}).get("results", [])
        )
        for entry in events:
            ev = entry.get("result") or {}
            ts = ev.get("origin_server_ts") or 0
            messages.append(
                {
                    "ts": datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    "msgtype": (ev.get("content") or {}).get("msgtype"),
                    "body": (ev.get("content") or {}).get("body", ""),
                }
            )

        next_batch = (
            result.get("search_categories", {}).get("room_events", {}).get("next_batch")
        )
        if not next_batch:
            break

    messages.sort(key=lambda m: m["ts"])
    for m in messages:
        ts = gray(f"[{m['ts'].isoformat()}]")
        suffix = gray(f"({m['msgtype']})") if m["msgtype"] else ""
        print(f"{ts} {m['body']} {suffix}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
