"""Reduce the verbose ``rooms.json`` snapshot into a small ``Room`` graph.

Mirrors the original ``lib/condensing.mjs`` from the matrix-tools project
but is fully Python/stdlib.  See ``synapse-fetch-rooms.py`` for the input
format (a list of ``{"room": …, "states": [state events …]}`` entries).

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# A join policy is one of:
#   "public"
#   "invite-only"
#   "unknown"
#   ("in-space", [allow_room_id, …])  — room version 9+ restricted joins
JoinPolicy = object  # documented above; kept as object for simplicity


@dataclass
class Room:
    id: str
    name: str
    version: int
    creator: Optional[str] = None
    join_policy: JoinPolicy = "public"
    space_children: list[str] = field(default_factory=list)
    permissions: dict[str, int] = field(default_factory=dict)
    members: dict[str, datetime] = field(default_factory=dict)
    is_encrypted: bool = False
    is_space: bool = False
    is_replaced: bool = False
    predecessor: Optional[str] = None


def condense(data: list[dict]) -> dict[str, Room]:
    """Convert a list of fetched rooms with their state events into a dict
    of ``Room`` objects keyed by room ID.

    Rooms with no human-readable name are skipped (they are usually direct
    messages or internal rooms with no meaningful identity).
    """
    rooms: dict[str, Room] = {}

    for entry in data:
        room = entry.get("room", {})
        states = entry.get("states", [])

        name = room.get("name")
        if not name:
            continue

        is_space = room.get("room_type") == "m.space"
        try:
            version = int(room.get("version", 0))
        except (TypeError, ValueError):
            version = 0

        r = Room(
            id=room["room_id"],
            name=name,
            version=version,
            is_encrypted=room.get("encryption") is not None,
            is_space=is_space,
        )
        rooms[r.id] = r

        for state in states:
            stype = state.get("type")
            content = state.get("content", {}) or {}

            if stype == "m.room.create":
                r.creator = content.get("creator") or state.get("sender")
                pred = content.get("predecessor")
                if isinstance(pred, dict) and pred.get("room_id"):
                    r.predecessor = pred["room_id"]

            elif stype == "m.room.tombstone" and content.get("replacement_room"):
                r.is_replaced = True

            elif stype == "m.space.child" and content:
                r.space_children.append(state.get("state_key", ""))

            elif stype == "m.room.join_rules":
                rule = content.get("join_rule")
                if rule == "public":
                    r.join_policy = "public"
                elif rule == "invite":
                    r.join_policy = "invite-only"
                elif rule == "restricted":
                    allow = content.get("allow") or []
                    room_ids = [
                        a["room_id"]
                        for a in allow
                        if isinstance(a, dict)
                        and a.get("type") == "m.room_membership"
                        and a.get("room_id")
                    ]
                    r.join_policy = ("in-space", room_ids)
                else:
                    r.join_policy = "unknown"

            elif stype == "m.room.power_levels":
                users = content.get("users") or {}
                for uid, level in users.items():
                    try:
                        r.permissions[uid] = int(level)
                    except (TypeError, ValueError):
                        continue

            elif (
                stype == "m.room.member"
                and content.get("membership") == "join"
                and state.get("state_key")
            ):
                ts = state.get("origin_server_ts")
                if isinstance(ts, (int, float)):
                    r.members[state["state_key"]] = datetime.fromtimestamp(
                        ts / 1000, tz=timezone.utc
                    )

    return rooms
