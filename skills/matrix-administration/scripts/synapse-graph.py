#!/usr/bin/env python3
"""Render a snapshot of rooms as a Graphviz graph.

Reads ``rooms.json`` (produced by ``synapse-fetch-rooms.py``), writes
``rooms.dot`` (Graphviz source) and — if the ``dot`` binary is available —
``rooms.svg``.

Each room is a node coloured by its rating (green/orange/red).  Spaces are
drawn with a green/blue gradient when healthy.  Edges go from child rooms
to their parent space.

Usage:
    synapse-graph.py [--input rooms.json] [--dot rooms.dot] [--svg rooms.svg] \\
        [--language en|de] [--space '!ID:server' …] [--no-svg]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    Room,
    RoomRating,
    condense,
    format_rating,
    load_config,
    rate_room,
)


_COLORS = {
    "blue": "#2222ff",
    "bright_blue": "#7777ff",
    "red": "#ff2222",
    "bright_red": "#ff7777",
    "green": "#22cc22",
    "bright_green": "#77ff77",
    "gray": "#222222",
    "orange": "#ff8800",
    "bright_orange": "#ffaa22",
}


def _enc(value: str) -> str:
    return (value or "").replace('"', '\\"')


def _join_policy_text(r: Room, rooms: dict[str, Room]) -> str:
    if isinstance(r.join_policy, tuple) and r.join_policy[0] == "in-space":
        names = [rooms[rid].name for rid in r.join_policy[1] if rid in rooms]
        return "members of " + ", ".join(names) if names else "members of (unknown)"
    if isinstance(r.join_policy, str):
        return r.join_policy
    return "unknown"


def _icon(r: Room) -> str:
    if r.join_policy == "public":
        return "🌐"
    if r.join_policy == "invite-only":
        return "🔒"
    return "🚀"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-i", "--input", default="rooms.json")
    parser.add_argument("--dot", default="rooms.dot")
    parser.add_argument("--svg", default="rooms.svg")
    parser.add_argument("-l", "--language", default=None, choices=["en", "de"])
    parser.add_argument(
        "-s",
        "--space",
        action="append",
        default=None,
        help="Space ID treated as 'home'. Repeatable.",
    )
    parser.add_argument(
        "--no-svg", action="store_true", help="Skip the dot → SVG step."
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

    lines: list[str] = ["digraph G {", '  graph [rankdir="LR"];']
    for r in rooms.values():
        if r.is_replaced:
            continue
        score, violations = rate_room(r, rooms, home_spaces, language)

        if score == RoomRating.SUCCESS:
            color = _COLORS["green"]
            fill = (
                f"{_COLORS['bright_green']}:{_COLORS['bright_blue']}"
                if r.is_space
                else _COLORS["bright_green"]
            )
        elif score == RoomRating.WARNING:
            color = _COLORS["orange"]
            fill = _COLORS["bright_orange"]
        else:
            color = _COLORS["red"]
            fill = _COLORS["bright_red"]

        creator = (r.creator or "unknown").split(":")[0]
        label = f"{_icon(r)} {_enc(r.name)}\\n(v{r.version}, {_join_policy_text(r, rooms)}, by {_enc(creator)})"
        tooltip = "\\n".join(format_rating(m) for m in violations)

        lines.append(
            f'  "{_enc(r.id)}" [label="{label}", style=filled, '
            f'color="{color}", fontcolor="black", fillcolor="{fill}", '
            f'tooltip="{_enc(tooltip)}", shape=rectangle, penwidth=3];'
        )
        for child_id in r.space_children:
            child = rooms.get(child_id)
            if not child or child.is_replaced:
                continue
            lines.append(
                f'  "{_enc(child_id)}" -> "{_enc(r.id)}" [label="space child"];'
            )

    lines.append("}")
    with open(args.dot, "w") as f:
        f.write("\n".join(lines) + "\n")

    if args.no_svg:
        print(f"Wrote {args.dot}")
        return 0

    if shutil.which("dot") is None:
        print(
            f"Wrote {args.dot}. Install Graphviz ('dot') to render the SVG, or pass --no-svg.",
            file=sys.stderr,
        )
        return 0

    try:
        subprocess.run(
            ["dot", "-Tsvg", args.dot, "-o", args.svg],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"dot failed: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {args.dot} and {args.svg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
