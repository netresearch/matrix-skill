"""Room health-check rules.

Each room is rated against a set of policies and earns one of three levels:

- ``SUCCESS``: rule satisfied
- ``WARNING``: minor / advisory issue
- ``FAIL``:    serious / blocking issue

Both English and German phrasings are provided.  The "is the room reachable
from one of our spaces" check requires a list of *home* space IDs to be
passed in by the caller — the skill itself ships no homeserver-specific data.

Stdlib only.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from _lib.condensing import Room


class RoomRating(IntEnum):
    SUCCESS = 0
    WARNING = 1
    FAIL = 2


def rating_emoji(rating: RoomRating) -> str:
    return {RoomRating.SUCCESS: "✅", RoomRating.WARNING: "⚠️", RoomRating.FAIL: "❌"}[
        rating
    ]


def format_rating(item: tuple[RoomRating, str]) -> str:
    rating, message = item
    return f"{rating_emoji(rating)} {message}"


_T = {
    "room": {
        "public": {
            "en": "Is a public room",
            "de": "Ist ein öffentlicher Raum",
        },
        "encryption": {
            "yes": {"en": "Encrypted", "de": "Verschlüsselt"},
            "no": {"en": "Not encrypted", "de": "Nicht verschlüsselt"},
        },
        "joinable-from-our-spaces": {
            "yes": {
                "en": "Joinable from our spaces",
                "de": "Von unseren Spaces aus beitretbar",
            },
            "no": {
                "en": "Not joinable from our spaces",
                "de": "Nicht von unseren Spaces aus beitretbar",
            },
        },
        "in-one-of-our-spaces": {
            "yes": {"en": "In one of our spaces", "de": "In einem unserer Spaces"},
            "no": {
                "en": "Not in one of our spaces",
                "de": "Nicht in einem unserer Spaces",
            },
            "predecessor-was": {
                "en": "Predecessor was in one of our spaces",
                "de": "Vorgänger war in einem unserer Spaces",
            },
        },
    },
    "space": {
        "public": {
            "en": "Is a public space",
            "de": "Ist ein öffentlicher Space",
        },
        "our": {
            "yes": {"en": "One of our spaces", "de": "Einer unserer Spaces"},
            "no": {"en": "Not one of our spaces", "de": "Nicht einer unserer Spaces"},
        },
    },
}


def rate_room(
    r: Room,
    rooms: dict[str, Room],
    home_space_ids: Optional[list[str]] = None,
    language: str = "en",
) -> tuple[RoomRating, list[tuple[RoomRating, str]]]:
    """Run health checks on a single room.

    Args:
        r: The room to rate.
        rooms: All rooms in the snapshot (used to look up parent spaces and
            predecessors).
        home_space_ids: List of "your" space IDs.  Rooms reachable from
            (or members of) one of these are treated as in-space.  When
            ``None`` or empty, the in-space checks degrade to "no opinion".
        language: ``"en"`` or ``"de"``.

    Returns:
        A tuple ``(overall, messages)``: the worst rating across all checks,
        and the per-check ``(rating, message)`` list.
    """
    if language not in ("en", "de"):
        language = "en"
    home = set(home_space_ids or [])

    messages: list[tuple[RoomRating, str]] = []

    def add(rating: RoomRating, message: str) -> None:
        messages.append((rating, message))

    if r.is_space:
        if r.join_policy == "public":
            add(RoomRating.FAIL, _T["space"]["public"][language])

        if isinstance(r.join_policy, tuple) and r.join_policy[0] == "in-space":
            allow_ids = r.join_policy[1]
            if home:
                if not any(rid in home for rid in allow_ids):
                    add(
                        RoomRating.FAIL,
                        _T["room"]["joinable-from-our-spaces"]["no"][language],
                    )
                else:
                    add(
                        RoomRating.SUCCESS,
                        _T["room"]["joinable-from-our-spaces"]["yes"][language],
                    )

        if home:
            if r.id not in home:
                add(RoomRating.WARNING, _T["space"]["our"]["no"][language])
            else:
                add(RoomRating.SUCCESS, _T["space"]["our"]["yes"][language])
    else:
        if r.join_policy == "public":
            add(RoomRating.FAIL, _T["room"]["public"][language])

        if (
            r.version > 9
            and isinstance(r.join_policy, tuple)
            and r.join_policy[0] == "in-space"
        ):
            allow_ids = r.join_policy[1]
            if home:
                if not any(rid in home for rid in allow_ids):
                    add(
                        RoomRating.FAIL,
                        _T["room"]["joinable-from-our-spaces"]["no"][language],
                    )
                else:
                    add(
                        RoomRating.SUCCESS,
                        _T["room"]["joinable-from-our-spaces"]["yes"][language],
                    )

        if home:
            if not _is_in_one_of(r, rooms, home):
                add(
                    RoomRating.WARNING,
                    _T["room"]["in-one-of-our-spaces"]["no"][language],
                )
                if r.predecessor:
                    pred = rooms.get(r.predecessor)
                    if pred and _is_in_one_of(pred, rooms, home):
                        add(
                            RoomRating.FAIL,
                            _T["room"]["in-one-of-our-spaces"]["predecessor-was"][
                                language
                            ],
                        )
            else:
                add(
                    RoomRating.SUCCESS,
                    _T["room"]["in-one-of-our-spaces"]["yes"][language],
                )

        if not r.is_encrypted:
            add(RoomRating.WARNING, _T["room"]["encryption"]["no"][language])
        else:
            add(RoomRating.SUCCESS, _T["room"]["encryption"]["yes"][language])

    overall = max((rating for rating, _ in messages), default=RoomRating.SUCCESS)
    return overall, messages


def _is_in_one_of(r: Room, rooms: dict[str, Room], home: set[str]) -> bool:
    """True iff *some* parent space of ``r`` is in ``home``."""
    for s in rooms.values():
        if r.id in s.space_children and s.id in home:
            return True
    return False
