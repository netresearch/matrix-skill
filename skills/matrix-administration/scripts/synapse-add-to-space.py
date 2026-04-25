#!/usr/bin/env python3
"""Link a room into a space.

Sends an ``m.space.child`` state event on the space with the room as the
state key.  The admin token must belong to a user that has permission to
send state events in the space (typically a space admin).

Usage:
    synapse-add-to-space.py <ROOM_ID> [SPACE_ID]

Falls back to ``$MATRIX_SPACE_ID`` and then to ``default_space_id`` from
the config when ``SPACE_ID`` is omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import client_request, load_config, quote


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("room_id")
    parser.add_argument("space_id", nargs="?", default=None)
    parser.add_argument(
        "--via",
        action="append",
        default=None,
        help="Server name to include in 'via'. Repeatable; defaults to the "
        "homeserver hostname.",
    )
    parser.add_argument("--suggested", action="store_true")
    args = parser.parse_args()

    config = load_config()
    space_id = (
        args.space_id
        or os.environ.get("MATRIX_SPACE_ID")
        or config.get("default_space_id")
    )
    if not space_id:
        print(
            "Error: SPACE_ID required (positional, $MATRIX_SPACE_ID, or "
            "'default_space_id' in config).",
            file=sys.stderr,
        )
        return 2

    via = args.via
    if not via:
        from urllib.parse import urlparse

        host = urlparse(config["homeserver"]).hostname
        via = [host] if host else []

    body = {"via": via, "suggested": args.suggested}
    endpoint = (
        f"/rooms/{quote(space_id)}/state/m.space.child/{quote(args.room_id)}"
    )
    result = client_request(config, "PUT", endpoint, body)
    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
