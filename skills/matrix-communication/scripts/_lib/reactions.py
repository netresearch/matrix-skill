# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Find the reactions one account set on one event.

A status reaction is replaced by redacting the old one, and a redaction needs
the reaction's own event id. The caller should not have to keep that id: the
server lists every annotation on an event (``/relations/{event}/m.annotation``),
and the account's own ones are picked out here by sender and key.

``m.relates_to`` stays in clear text on an encrypted event, so an encrypted
reaction (``m.room.encrypted``) carries its key where this code reads it.
"""

from collections.abc import Callable, Iterable
from urllib.parse import quote


def path_segment(value: str) -> str:
    # Same encoding as _lib.http.path_segment; repeated so this module stays
    # importable on its own, the way its test file loads it.
    return quote(str(value), safe="")


# Synapse caps a page at 1000; one notification rarely carries more than a
# handful, so this is a guard against a server that never stops paging.
MAX_PAGES = 50


def own_reactions(
    events: Iterable[dict], user_id: str, keys: set[str] | None
) -> list[dict]:
    """Return ``{"event_id", "key"}`` for each live reaction ``user_id`` set
    with one of ``keys``; ``keys=None`` returns every key.

    A reaction that was already redacted no longer counts: its content is gone,
    and redacting it again would only produce a second, useless event.
    """
    found = []
    for event in events:
        if event.get("sender") != user_id:
            continue
        if event.get("type") not in ("m.reaction", "m.room.encrypted"):
            continue
        if "redacted_because" in event.get("unsigned", {}):
            continue
        relation = event.get("content", {}).get("m.relates_to", {})
        if relation.get("rel_type") != "m.annotation":
            continue
        key = relation.get("key")
        if (keys is None or key in keys) and event.get("event_id"):
            found.append({"event_id": event["event_id"], "key": key})
    return found


def annotations(
    request: Callable[[str], dict], room_id: str, event_id: str
) -> list[dict] | dict:
    """Every annotation event on ``event_id``, following pagination.

    ``request`` takes a client-API v1 path and returns the parsed response.
    Returns the error dict of the first failing page, so a failed lookup can
    never pass for "no reactions there".
    """
    base = (
        f"/rooms/{path_segment(room_id)}/relations/{path_segment(event_id)}"
        "/m.annotation?limit=100"
    )
    events: list[dict] = []
    token = None
    for _ in range(MAX_PAGES):
        path = base if token is None else f"{base}&from={quote(token, safe='')}"
        page = request(path)
        if "error" in page:
            return page
        events.extend(page.get("chunk", []))
        token = page.get("next_batch")
        if not token:
            return events
    return {"error": f"more than {MAX_PAGES} pages of reactions on {event_id}"}
