#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""React to a Matrix message with an emoji.

Usage:
    matrix-react.py ROOM EVENT_ID EMOJI [--replace OLD ...]
    matrix-react.py ROOM EVENT_ID EMOJI --remove
    matrix-react.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name
    EVENT_ID    Event ID of message to react to (e.g., $abc123...)
    EMOJI       Emoji reaction (e.g., checkmark, thumbsup, party)

Options:
    --replace OLD [OLD ...]
                Status swap: set EMOJI, then remove this account's own
                reactions with any of OLD on the same event. EMOJI is not
                sent twice when this account already set it.
    --remove    Remove this account's own EMOJI reaction instead of adding one
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help

The script looks up the account's own reactions on the server, so the caller
never needs a reaction's event id.

Examples:
    # Add checkmark reaction
    matrix-react.py "#ops:matrix.org" "$eventid" "checkmark"

    # Move a ticket notification from "working" to "done"
    matrix-react.py "#ops:matrix.org" "$eventid" "✅" --replace "▶️" "🩹"

    # Take a reaction back
    matrix-react.py "#dev:matrix.org" "$eventid" "▶️" --remove
"""

import json
import os
import sys
import time

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    annotations,
    clean_message,
    daemon_request,
    find_room_by_name,
    load_config,
    matrix_request,
    normalize_room_input,
    own_reactions,
    path_segment,
    resolve_room_alias,
)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def send_reaction(
    config: dict,
    room_id: str,
    event_id: str,
    emoji: str,
    trust_unverified_devices: bool = False,
) -> dict:
    """Send a reaction to a message.

    Reactions use the m.reaction event type with m.annotation relation.
    """
    # A running daemon owns the account's credentials, so let it send. The
    # signal is a socket that answers, never the store lock: a direct send holds
    # that lock too, and routing on it would aim at a socket nobody serves.
    # None means nothing is listening; an error response is an answer and is
    # returned, because falling through on it would react twice.
    response = daemon_request(
        {
            "op": "react",
            "room": room_id,
            "event_id": event_id,
            "key": emoji,
            "trust_unverified_devices": trust_unverified_devices,
        }
    )
    if response is not None:
        if response.get("ok"):
            return {"event_id": response["event_id"]}
        return {"error": response.get("error", "daemon refused the reaction")}

    txn_id = str(int(time.time() * 1000))

    content = {
        "m.relates_to": {"rel_type": "m.annotation", "event_id": event_id, "key": emoji}
    }

    return matrix_request(
        config,
        "PUT",
        f"/rooms/{path_segment(room_id)}/send/m.reaction/{txn_id}",
        content,
    )


def redact_reaction(config: dict, room_id: str, reaction_id: str) -> dict:
    """Redact one reaction event; same routing as matrix-redact.py."""
    response = daemon_request(
        {"op": "redact", "room": room_id, "event_id": reaction_id, "reason": None}
    )
    if response is not None:
        if response.get("ok"):
            return {"event_id": response["event_id"]}
        return {"error": response.get("error", "daemon refused the redaction")}
    txn_id = str(int(time.time() * 1000))
    return matrix_request(
        config,
        "PUT",
        f"/rooms/{path_segment(room_id)}/redact/{path_segment(reaction_id)}/{txn_id}",
        {},
    )


def own_user_id(config: dict) -> str | dict:
    """The account's user ID: from the config, else asked of the server."""
    if config.get("user_id"):
        return config["user_id"]
    whoami = matrix_request(config, "GET", "/account/whoami")
    if "error" in whoami:
        return whoami
    return whoami.get("user_id") or {"error": "whoami returned no user_id"}


def find_own(
    config: dict, room_id: str, event_id: str, keys: set | None
) -> list | dict:
    """This account's live reactions with one of ``keys`` on ``event_id``
    (every key when ``keys`` is None)."""
    user_id = own_user_id(config)
    if isinstance(user_id, dict):
        return user_id
    events = annotations(
        lambda path: matrix_request(config, "GET", path, api_version="v1"),
        room_id,
        event_id,
    )
    if isinstance(events, dict):
        return events
    return own_reactions(events, user_id, keys)


def apply_reaction(
    config: dict,
    room_id: str,
    event_id: str,
    emoji: str,
    replace: list[str],
    remove: bool,
    trust_unverified_devices: bool = False,
) -> dict:
    """Add, swap or remove a reaction; returns what was sent and redacted."""
    if not replace and not remove:
        return send_reaction(config, room_id, event_id, emoji, trust_unverified_devices)

    drop = {emoji} if remove else set(replace) - {emoji}
    found = find_own(config, room_id, event_id, drop | {emoji})
    if isinstance(found, dict):
        return {
            "error": f"could not read the reactions on {event_id}: {found['error']}"
        }

    result: dict = {"event_id": None, "removed": []}
    if not remove:
        existing = [r["event_id"] for r in found if r["key"] == emoji]
        if existing:
            # Matrix rejects a second identical annotation; keep the first.
            result["event_id"] = existing[0]
        else:
            sent = send_reaction(
                config, room_id, event_id, emoji, trust_unverified_devices
            )
            if "error" in sent:
                # Leave the old status in place: no status is worse than a stale one.
                return sent
            result["event_id"] = sent.get("event_id")

    return redact_keys(config, room_id, found, drop, result)


def redact_keys(
    config: dict, room_id: str, found: list, drop: set, result: dict
) -> dict:
    """Redact the reactions in ``found`` whose key is in ``drop``; stop at the first failure."""
    for reaction in found:
        if reaction["key"] not in drop:
            continue
        redacted = redact_reaction(config, room_id, reaction["event_id"])
        if "error" in redacted:
            result["error"] = (
                f"could not remove {reaction['key']} ({reaction['event_id']}): "
                f"{redacted['error']}"
            )
            return result
        result["removed"].append(reaction["key"])
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="React to a Matrix message with an emoji"
    )
    parser.add_argument(
        "room", help="Room alias (#room:server), room ID (!id:server), or room name"
    )
    parser.add_argument("event_id", help="Event ID of message to react to")
    parser.add_argument(
        "emoji",
        nargs="?",
        help="Emoji reaction (e.g., checkmark, thumbsup, party); not with --list",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--replace",
        nargs="+",
        default=[],
        metavar="OLD",
        help="Set EMOJI, then remove this account's own reactions with any of OLD "
        "on the same event (a status swap)",
    )
    mode.add_argument(
        "--remove",
        action="store_true",
        help="Remove this account's own EMOJI reaction instead of adding one",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="Print this account's own live reactions on the event (emoji and "
        "reaction event ID) and change nothing",
    )
    parser.add_argument(
        "--trust-unverified-devices",
        action="store_true",
        help="When the daemon sends the reaction into an encrypted room, share its "
        "room key with devices that are not verified (default: refuse)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()
    if args.list and args.emoji:
        parser.error("--list takes no EMOJI")
    if not args.list and not args.emoji:
        parser.error("EMOJI is required unless --list is given")

    config = load_config()

    # Clean and resolve room
    room_input = normalize_room_input(clean_message(args.room))
    room_id = room_input

    if room_input.startswith("!"):
        # Direct room ID
        room_id = room_input
        if args.debug:
            print(f"Using room ID directly: {room_id}", file=sys.stderr)
    elif room_input.startswith("#"):
        # Room alias
        try:
            room_id = resolve_room_alias(config, room_input)
            if args.debug:
                print(f"Resolved {room_input} -> {room_id}", file=sys.stderr)
        except ValueError as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Room name lookup
        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room_id = found_id
            if args.debug:
                print(f"Found room: {room_id}", file=sys.stderr)
        else:
            error_msg = f"Could not find room '{room_input}'"
            if matches:
                error_msg += ". Multiple matches found:\n"
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
            else:
                error_msg += ". Use 'matrix-rooms.py' to list available rooms."
            if args.json:
                print(json.dumps({"error": error_msg}))
            else:
                print(f"Error: {error_msg}", file=sys.stderr)
            sys.exit(1)

    if args.list:
        found = find_own(config, room_id, args.event_id, None)
        if isinstance(found, dict):
            message = (
                f"could not read the reactions on {args.event_id}: {found['error']}"
            )
            if args.json:
                print(json.dumps({"error": message}))
            else:
                print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps({"reactions": found}))
        else:
            for item in found:
                print(f"{item['key']}\t{item['event_id']}")
        return

    result = apply_reaction(
        config,
        room_id,
        args.event_id,
        args.emoji,
        replace=args.replace,
        remove=args.remove,
        trust_unverified_devices=args.trust_unverified_devices,
    )

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    elif args.quiet:
        print(result.get("event_id") or "")
    elif args.remove:
        removed = len(result["removed"])
        print(f"Removed {removed} {args.emoji} reaction(s) from {args.event_id}")
    else:
        print(f"Reacted with {args.emoji} to {args.event_id}")
        print(f"Event ID: {result.get('event_id')}")
        if result.get("removed"):
            print(f"Removed: {' '.join(result['removed'])}")


if __name__ == "__main__":
    main()
