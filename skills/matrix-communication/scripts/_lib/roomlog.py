"""Room event log: slugs, records, append, and the reader's cursor.

Stdlib only, deliberately. The reader that follows a log must not depend on nio
or on an external binary - it is the part that runs in every agent session,
often several at once, and it must stay cheap enough that starting one is not a
decision.

The log is JSONL rather than this repository's usual OKF: OKF defines one
concept per file with no provision for streams, and its log.md is ordered
newest-first, so every append would rewrite the whole file. See
docs/specs/2026-08-13-live-room-awareness.md.
"""

import json
import re
from datetime import datetime, timezone

TEXT_LIMIT = 220
DEFAULT_MAX_BYTES = 8_000_000


def room_slug(room_id: str) -> str:
    """Filename-safe form of a room id.

    A `!` in a filename is a hazard in every shell invocation that touches it,
    and `/` is not a filename character at all.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", room_id.lstrip("!"))


def _mentions(body, own_user_id: str, own_display_name) -> bool:
    """Whether this body addresses us.

    Word-bounded on purpose: a localpart that appears inside a longer word -
    "basti" in "bastion" - is not a mention, and a summary that counts those is
    a summary nobody trusts.
    """
    if not body:
        return False
    localpart = own_user_id.split(":")[0].lstrip("@")
    for needle in (n for n in (localpart, own_display_name) if n):
        if re.search(rf"\b{re.escape(needle)}\b", body, re.IGNORECASE):
            return True
    return False


def _localpart(user_id: str) -> str:
    """`@name:server` without the decoration.

    The fallback when no display name is known, which in a large room is the
    normal case rather than an edge one: member state arrives lazily, so the
    first events of a session routinely have nothing to render. The whole MXID
    costs a third of a line, and line width is what keeps a busy room readable.
    The record itself keeps the full id.
    """
    return user_id.split(":")[0].lstrip("@")


def render_text(record: dict) -> str:
    """The single line a reader prints, built once by the daemon.

    Whitespace is folded: the reader prints one record per line, so a body
    carrying newlines would otherwise arrive as several lines that no longer
    correspond to one event.
    """
    # Local time, said explicitly: the reader is a person looking at a clock on
    # the same machine. The conversion goes through UTC so the intent is in the
    # code rather than in whatever the process default happens to be.
    when = datetime.fromtimestamp(record["ts"] / 1000, tz=timezone.utc).astimezone()
    stamp = when.strftime("%H:%M")
    who = record.get("sender_display") or _localpart(record["sender"])
    if record.get("self") and record.get("self_basis") == "device":
        # The log is read by the agent that wrote part of it. Without this the
        # agent's own lines are indistinguishable from its human's, because the
        # account and therefore the display name are the same.
        who = f"{who} (agent)"
    body = " ".join((record.get("body") or "").split())

    if record["type"] == "encrypted":
        return f"[{stamp}] {who}: [unable to decrypt]"
    if record["type"] == "reaction":
        return f"[{stamp}] {who} reacted {body}".rstrip()
    if record["type"] == "redaction":
        return f"[{stamp}] {who} removed a message"
    if record["type"] == "membership":
        return f"[{stamp}] {who}: {body}".rstrip()

    if len(body) > TEXT_LIMIT:
        body = body[: TEXT_LIMIT - 1] + "…"
    prefix = "* " if record["type"] == "m.emote" else ""
    return f"[{stamp}] {who}: {prefix}{body}"


def _is_own_device(event: dict, own_user_id: str, own_sender_key) -> tuple[bool, str]:
    """Did THIS device send the event, and on what evidence.

    An agent and the person it works for share one Matrix account, so comparing
    the sender is not enough: it marks the human's messages as the agent's own.
    An agent that then skips "its own" messages skips the person addressing it,
    and one that does not can answer itself.

    A decrypted event carries `sender_key`, the curve25519 key of the device
    that encrypted it, and that is the answer. An unencrypted room has no such
    key; the account comparison is then all there is, and the second return
    value says which of the two was possible so a caller never mistakes one for
    the other.
    """
    if event["sender"] != own_user_id:
        return False, "device" if event.get(
            "sender_key"
        ) and own_sender_key else "account"
    if event.get("sender_key") and own_sender_key:
        return event["sender_key"] == own_sender_key, "device"
    return True, "account"


def build_record(
    *, seq: int, event: dict, own_user_id: str, own_display_name, own_sender_key=None
) -> dict:
    """One log record from one event."""
    is_self, basis = _is_own_device(event, own_user_id, own_sender_key)
    record = {
        "seq": seq,
        "ts": event["ts"],
        "event_id": event["event_id"],
        "room_id": event.get("room_id"),
        "sender": event["sender"],
        "sender_display": event.get("sender_display"),
        "type": event["type"],
        "body": event.get("body"),
        "reply_to": event.get("reply_to"),
        "thread_root": event.get("thread_root"),
        "self": is_self,
        "self_basis": basis,
        "mentions_me": _mentions(event.get("body"), own_user_id, own_display_name),
    }
    if event.get("session_id"):
        record["session_id"] = event["session_id"]
    record["text"] = render_text(record)
    return record


def log_path(rooms_dir, room_id: str):
    """Path of a room's log. `rooms_dir` is a pathlib.Path."""
    rooms_dir.mkdir(parents=True, exist_ok=True)
    return rooms_dir / f"{room_slug(room_id)}.jsonl"


def _rotated(path):
    """The single retained previous generation of a log."""
    return path.with_name(path.name + ".1")


def read_records(path):
    """Yield records oldest first.

    A truncated final line - a daemon killed mid-write - is skipped rather than
    ending the read: one lost record must not cost the whole log.
    """
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def next_seq(path) -> int:
    """One past the highest seq, counting the rotated generation too.

    Rotation must not restart numbering: the cursor reports what was missed by
    subtracting, and a reset would silently report a gap of zero.
    """
    highest = 0
    for candidate in (_rotated(path), path):
        for record in read_records(candidate):
            highest = max(highest, record.get("seq", 0))
    return highest + 1


def append_record(path, record: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Append one record, rotating first once the log passes `max_bytes`.

    One generation is kept. The reader follows the path by name, so rotation is
    invisible to it.
    """
    if path.exists() and path.stat().st_size >= max_bytes:
        path.replace(_rotated(path))
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def cursor_path(rooms_dir, room_id: str, name: str = "default"):
    """Where one reader's position in a room log is kept."""
    rooms_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return rooms_dir / f"{room_slug(room_id)}.{safe}.cursor"


def read_cursor(path) -> int:
    """The last seq this reader saw, or 0 when it has never read one.

    An unreadable or damaged cursor also reads as 0: showing a backlog twice is
    recoverable, skipping it silently is not.
    """
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def write_cursor(path, seq: int) -> None:
    path.write_text(f"{seq}\n")


def summarize_since(log, seq: int) -> dict:
    """What arrived after `seq`.

    `truncated` means the oldest record still in the log is already newer than
    the cursor, so the counts are a lower bound - rotation carried the rest
    away and the exact number is not knowable from the log alone. Reporting it
    as exact would be the kind of number that hides what it does not know.
    """
    total = 0
    mentions = 0
    last_seq = seq
    oldest_seen = None

    for record in read_records(log):
        record_seq = record.get("seq", 0)
        if oldest_seen is None:
            oldest_seen = record_seq
        last_seq = max(last_seq, record_seq)
        if record_seq > seq:
            total += 1
            if record.get("mentions_me"):
                mentions += 1

    truncated = bool(seq and oldest_seen is not None and oldest_seen > seq + 1)
    return {
        "total": total,
        "mentions": mentions,
        "last_seq": last_seq,
        "truncated": truncated,
    }


def write_room_bundle(directory, rooms: dict) -> None:
    """Describe the watched rooms as an OKF bundle.

    Rooms are knowledge, not a stream, so they take the repository's normal
    format: typed frontmatter per room and an index that lists them. This also
    replaces what would otherwise be an ad-hoc slug-to-room mapping nobody
    could read. See https://okf.md/.

    Lives here rather than in the daemon so it can be tested without nio.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).isoformat()
    entries = []

    for room_id, label in sorted(rooms.items(), key=lambda item: item[1]):
        slug = room_slug(room_id)
        description = f"Matrix room {label}, watched by matrix-watchd."
        (directory / f"{slug}.md").write_text(
            "---\n"
            "type: matrix-room\n"
            f"title: {label}\n"
            f"description: {description}\n"
            f"resource: matrix:roomid/{room_id.lstrip('!')}\n"
            "tags: [matrix, room, watched]\n"
            f"timestamp: {stamp}\n"
            "---\n\n"
            f"# {label}\n\n"
            f"Room ID `{room_id}`. Events are appended to `{slug}.jsonl`;\n"
            "follow them with `matrix-watch.py`.\n",
            encoding="utf-8",
        )
        entries.append(f"- [{label}]({slug}.md) - {description}")

    (directory / "index.md").write_text(
        "# Watched rooms\n\n"
        "Written by `matrix-watchd.py`. Each room's events are in the "
        "`.jsonl` file next to its page.\n\n" + "\n".join(entries) + "\n",
        encoding="utf-8",
    )
