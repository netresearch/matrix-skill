#!/usr/bin/env python3
"""Rate every room in a snapshot and print the failing ones.

Reads ``rooms.json`` (produced by ``synapse-fetch-rooms.py``), runs the
health-check rules from ``_lib/rating.py`` against every non-replaced room,
and prints two formatted lists of rooms with at least one ``FAIL`` finding:

1. Jira wiki markup
2. Markdown

Use ``--language de`` for German phrasing.  Pass ``--space`` one or more
times (or set ``default_space_id``/``home_space_ids`` in the config) to
enable the "is in one of our spaces" checks; without it those checks are
skipped.

Usage:
    synapse-rate-rooms.py [--input rooms.json] [--language en|de] \\
        [--space '!ID:server' …]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    RoomRating,
    condense,
    format_rating,
    load_config,
    rate_room,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-i", "--input", default="rooms.json")
    parser.add_argument("-l", "--language", default=None, choices=["en", "de"])
    parser.add_argument(
        "-s",
        "--space",
        action="append",
        default=None,
        help="Space ID treated as 'home'. Repeatable.",
    )
    args = parser.parse_args()

    config = load_config(require_admin=False)

    language = args.language or os.environ.get("LANGUAGE", "en")
    if language not in ("en", "de"):
        language = "en"

    home_spaces: list[str] = list(args.space or [])
    if not home_spaces:
        cfg_home = config.get("home_space_ids") or []
        if isinstance(cfg_home, list):
            home_spaces.extend(cfg_home)
        if config.get("default_space_id"):
            home_spaces.append(config["default_space_id"])

    with open(args.input) as f:
        data = json.load(f)
    rooms = condense(data)

    flagged = []
    for r in rooms.values():
        if r.is_replaced:
            continue
        overall, messages = rate_room(r, rooms, home_spaces, language)
        ratings = [m for m in messages if m[0] != RoomRating.SUCCESS]
        if any(rating == RoomRating.FAIL for rating, _ in ratings):
            flagged.append((r, ratings))

    flagged.sort(key=lambda pair: pair[0].name.strip().lower())

    def render(formatter):
        return "\n".join(formatter(r, ratings) for r, ratings in flagged)

    def jira(r, ratings):
        head = f"{{task}}{r.name.strip()} (v{r.version}){{task}}"
        body = "\n".join(f"** {format_rating(m)}" for m in ratings)
        return f"{head}\n{body}" if body else head

    def markdown(r, ratings):
        head = f"- {r.name.strip()} (v{r.version})"
        body = "\n".join(f"  {format_rating(m)}" for m in ratings)
        return f"{head}\n{body}" if body else head

    print(render(jira))
    print("\n\n")
    print(render(markdown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
