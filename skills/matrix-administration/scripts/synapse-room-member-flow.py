#!/usr/bin/env python3
"""Reconstruct the join/leave timeline of a room.

Walks the room's current state events (``GET .../rooms/{room_id}/state``)
and, for each non-join membership event, retrieves the event it replaced
to recover the original join timestamp.  Output is sorted chronologically.

If a ``--server`` suffix is given (or ``room_filter`` is configured), users
matching that suffix are highlighted in green; everyone else is red.

Usage:
    synapse-room-member-flow.py <ROOM_ID> [--server :example.com]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import bold, client_request, gray, green, load_config, quote, red


def _get_event(config: dict, room_id: str, sender: str, event_id: str) -> dict | None:
    filt = json.dumps({"senders": [sender]})
    endpoint = (
        f"/rooms/{quote(room_id)}/context/{quote(event_id)}"
        f"?limit=1&filter={quote(filt)}"
    )
    res = client_request(config, "GET", endpoint)
    if isinstance(res, dict):
        return res.get("event")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("--server", default=None)
    args = parser.parse_args()

    config = load_config()
    suffix = args.server if args.server is not None else config.get("room_filter", "")

    state = client_request(config, "GET", f"/rooms/{quote(args.room_id)}/state")
    if isinstance(state, dict) and "error" in state:
        print(f"Error: {state['error']}", file=sys.stderr)
        return 1
    if not isinstance(state, list):
        # The /state endpoint returns a list; some implementations wrap it.
        state = state.get("state", []) if isinstance(state, dict) else []

    events: list[tuple[datetime, str, str, str | None]] = []
    for s in state:
        if s.get("type") != "m.room.member":
            continue
        ts = datetime.fromtimestamp(
            (s.get("origin_server_ts") or 0) / 1000, tz=timezone.utc
        )
        membership = (s.get("content") or {}).get("membership")
        state_key = s.get("state_key")
        if not state_key:
            continue

        if membership == "join":
            display = (s.get("content") or {}).get("displayname")
            events.append((ts, "join", state_key, display))
        else:
            replaces = s.get("replaces_state")
            if replaces:
                old = _get_event(config, args.room_id, state_key, replaces)
                if old:
                    old_ts = datetime.fromtimestamp(
                        (old.get("origin_server_ts") or 0) / 1000, tz=timezone.utc
                    )
                    old_name = (old.get("content") or {}).get("displayname")
                    events.append((old_ts, "join", state_key, old_name))
                    events.append((ts, "leave", state_key, old_name))
                    continue
            events.append((ts, membership or "leave", state_key, None))

    events.sort(key=lambda e: e[0])

    for ts, kind, uid, name in events:
        ts_str = gray(ts.isoformat())
        is_local = bool(suffix) and uid.endswith(suffix)
        color = green if is_local else red
        label = uid + (f" ({name})" if name else "")
        user = bold(color(label))
        if kind == "join":
            arrow = bold(green("→"))
        else:
            arrow = bold(red("←"))
        print(f"{ts_str} {arrow} {user}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
