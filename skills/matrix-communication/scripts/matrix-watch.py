#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Follow a room's event log.

Prints one line per event on stdout, which is the shape a monitoring mechanism
consumes. It reads a file the daemon writes and never opens the E2EE store, so
any number of these can run at once and none of them can disturb a send.

Usage:
    matrix-watch.py ROOM [--cursor NAME] [--no-summary] [--once]

Requires matrix-watchd.py to be running and watching the room.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    cursor_path,
    load_config,
    log_path,
    read_cursor,
    read_records,
    resolve_room_cli,
    rooms_dir,
    summarize_since,
    write_cursor,
)

sys.stdout.reconfigure(line_buffering=True)

POLL_SECONDS = 0.5


def print_summary(log, seen: int) -> None:
    """One line about what was missed, or nothing when nothing was."""
    summary = summarize_since(log, seen)
    if not summary["total"]:
        return
    about = "at least " if summary["truncated"] else ""
    print(
        f"since last: {about}{summary['total']} messages, "
        f"{summary['mentions']} mentioning you"
    )


def drain(log, cursor, seen: int) -> int:
    """Print records newer than `seen`, return the new position."""
    for record in read_records(log):
        if record.get("seq", 0) > seen:
            print(record["text"])
            seen = record["seq"]
    write_cursor(cursor, seen)
    return seen


def _follow_open_file(handle, log, cursor, seen: int) -> int:
    """Read one open log until it is replaced. Returns the position reached.

    Returning on rotation rather than reopening in place keeps the file handle
    inside a single `with`, so there is no path where an exception leaves it
    open.
    """
    handle.seek(0, os.SEEK_END)
    inode = os.fstat(handle.fileno()).st_ino

    while True:
        line = handle.readline()
        if line:
            try:
                record = json.loads(line)
            except ValueError:
                # A record still being written. It will be complete on the next
                # pass; abandoning the log over it would not.
                continue
            print(record["text"])
            seen = max(seen, record.get("seq", 0))
            write_cursor(cursor, seen)
            continue

        time.sleep(POLL_SECONDS)
        try:
            if os.stat(log).st_ino != inode:
                return seen
        except FileNotFoundError:
            # Rotation, between the replace and the create. Keep reading this
            # handle and look again next pass.
            continue


def follow(log, cursor, seen: int) -> None:
    """Tail the log, following the path across rotation the way tail -F does."""
    while True:
        with open(log, encoding="utf-8") as handle:
            seen = _follow_open_file(handle, log, cursor, seen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Follow a room's event log")
    parser.add_argument("room", help="Room name, alias or ID")
    parser.add_argument(
        "--cursor",
        default="default",
        help="Name this reader's position, so several sessions can follow one room",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip the 'since last' line and start straight from the backlog",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print what is new and exit instead of following",
    )
    args = parser.parse_args()

    config = load_config()
    room_id = resolve_room_cli(config, args.room)
    directory = rooms_dir()
    log = log_path(directory, room_id)
    cursor = cursor_path(directory, room_id, args.cursor)

    if not log.exists():
        print(
            f"No log for {room_id}.\n"
            "Start the daemon and add the room to watch_rooms:\n"
            "  matrix-watchd.py --start",
            file=sys.stderr,
        )
        return 1

    seen = read_cursor(cursor)
    if not args.no_summary:
        print_summary(log, seen)

    seen = drain(log, cursor, seen)
    if args.once:
        return 0

    try:
        follow(log, cursor, seen)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
