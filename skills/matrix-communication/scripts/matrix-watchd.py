#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]<0.26"]
# ///
"""Watch daemon: the only process that holds the E2EE store.

Syncs, decrypts, appends every event of a watched room to that room's log, and
serves send/react/redact over a Unix socket. Everything else in the skill either
reads those logs or talks to this socket.

Why a daemon at all: two nio processes on one store corrupt it, and whichever
process syncs consumes the account's to-device events - the room keys and
verification requests - for every other process. One owner removes both failure
modes by construction rather than by convention. See
docs/specs/2026-08-13-live-room-awareness.md.

Usage:
    matrix-watchd.py --start | --stop | --status | --foreground

Rooms come from `watch_rooms` in ~/.config/matrix/config.json.
"""

import argparse
import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    append_record,
    build_mentions,
    build_record,
    check_e2ee_dependencies,
    daemon_request,
    get_store_path,
    inject_pills,
    load_config,
    load_credentials,
    log_path,
    markdown_to_html,
    next_seq,
    prefer_ipv4,
    resolve_room_alias,
    restore_login_checked,
    rooms_dir,
    socket_path,
    store_lock,
    suppress_nio_logging,
    write_room_bundle,
)

check_e2ee_dependencies()

from nio import (  # nio must not be imported before the dependency check
    AsyncClient,
    AsyncClientConfig,
    MegolmEvent,
    ReactionEvent,
    RedactionEvent,
    RoomMemberEvent,
    RoomMessageEmote,
    RoomMessageNotice,
    RoomMessageText,
)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

SYNC_TIMEOUT_MS = 30000


def lock_file_path():
    return get_store_path() / ".daemon.lock"


def pid_file_path():
    return socket_path().parent / "daemon.pid"


def _display_name(room, event, known_names):
    """The sender's display name, remembered once it has been seen.

    `room.user_name()` answers from member state, and in a large room that
    state arrives lazily - the first events of a session have nothing to render
    even for people the room has known for years. Caching what it does answer
    means one unnamed line per sender instead of every line for the length of
    the run. A membership event carrying a new name overwrites the entry.
    """
    sender = getattr(event, "sender", None)
    if not sender:
        return None
    name = room.user_name(sender)
    if known_names is None:
        return name
    if name:
        known_names[sender] = name
        return name
    return known_names.get(sender)


def event_to_dict(room, event, known_names=None) -> dict | None:
    """Map a nio event onto the plain dict `build_record` consumes.

    Returns None for event types the log does not carry, so the caller can tell
    "nothing to write" from "something went wrong".
    """
    base = {
        "event_id": getattr(event, "event_id", None),
        "sender": getattr(event, "sender", None),
        "sender_display": _display_name(room, event, known_names),
        "ts": getattr(event, "server_timestamp", None) or int(time.time() * 1000),
        "room_id": room.room_id,
        # The curve25519 key of the device that encrypted this, which is the
        # only thing that distinguishes our own messages from our human's -
        # they share the account. Absent in an unencrypted room.
        "sender_key": getattr(event, "sender_key", None),
    }
    if not base["event_id"] or not base["sender"]:
        return None

    if isinstance(event, RoomMessageText):
        source = event.source.get("content", {})
        relates = source.get("m.relates_to", {}) or {}
        return {
            **base,
            "type": "m.text",
            "body": event.body,
            "reply_to": (relates.get("m.in_reply_to") or {}).get("event_id"),
            "thread_root": relates.get("event_id")
            if relates.get("rel_type") == "m.thread"
            else None,
        }
    if isinstance(event, RoomMessageNotice):
        return {**base, "type": "m.notice", "body": event.body}
    if isinstance(event, RoomMessageEmote):
        return {**base, "type": "m.emote", "body": event.body}
    if isinstance(event, ReactionEvent):
        return {**base, "type": "reaction", "body": event.key}
    if isinstance(event, RedactionEvent):
        return {**base, "type": "redaction", "body": None}
    if isinstance(event, RoomMemberEvent):
        return {**base, "type": "membership", "body": event.membership}
    if isinstance(event, MegolmEvent):
        return {
            **base,
            "type": "encrypted",
            "body": None,
            "session_id": event.session_id,
        }
    return None


class Daemon:
    def __init__(self, config: dict, credentials: dict):
        self.config = config
        self.credentials = credentials
        self.client = None
        self.rooms = {}
        self.started = time.time()
        self.last_sync = None
        self.display_name = None
        self.own_sender_key = None
        self.known_names = {}
        self.stopping = asyncio.Event()
        self.next_seq_by_room = {}

    # -- logging -----------------------------------------------------------

    def record_event(self, room_id: str, event_dict: dict) -> None:
        """Append one event to its room's log.

        The sequence number is read from the log once per room and then carried
        in memory. Asking `next_seq` every time would re-read the whole log -
        and its rotated generation - for every incoming message, which on a log
        of tens of thousands of records means parsing megabytes per message in
        a busy room.

        Safe to cache because the daemon is the only writer: it holds the store
        lock for its whole run, and nothing else appends to these logs.
        """
        path = log_path(rooms_dir(), room_id)
        seq = self.next_seq_by_room.get(room_id)
        if seq is None:
            seq = next_seq(path)

        record = build_record(
            seq=seq,
            event=event_dict,
            own_user_id=self.credentials["user_id"],
            own_display_name=self.display_name,
            own_sender_key=self.own_sender_key,
        )
        append_record(path, record)
        self.next_seq_by_room[room_id] = seq + 1

    def announce(self, text: str) -> None:
        """Put a daemon-level message into every watched log.

        A watcher that dies quietly is indistinguishable from a quiet room, so
        the reason has to travel the same path the messages do.
        """
        for room_id in self.rooms:
            self.record_event(
                room_id,
                {
                    "event_id": f"$daemon-{int(time.time() * 1000)}",
                    "sender": self.credentials["user_id"],
                    "sender_display": "matrix-watchd",
                    "type": "m.notice",
                    "body": text,
                    "ts": int(time.time() * 1000),
                    "room_id": room_id,
                },
            )

    # -- callbacks ---------------------------------------------------------

    async def on_event(self, room, event) -> None:
        if room.room_id not in self.rooms:
            return
        event_dict = event_to_dict(room, event, self.known_names)
        if event_dict:
            self.record_event(room.room_id, event_dict)

    # -- socket ------------------------------------------------------------

    async def handle_client(self, reader, writer) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            try:
                request = json.loads(line)
            except ValueError:
                response = {"ok": False, "error": "malformed request"}
            else:
                response = await self.dispatch(request)
            writer.write(json.dumps(response).encode("utf-8") + b"\n")
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def dispatch(self, request: dict) -> dict:
        op = request.get("op")
        try:
            if op == "status":
                return {
                    "ok": True,
                    "pid": os.getpid(),
                    "uptime_seconds": int(time.time() - self.started),
                    "rooms": list(self.rooms),
                    "last_sync": self.last_sync,
                }
            if op == "send":
                return await self.op_send(request)
            if op == "react":
                return await self.op_react(request)
            if op == "edit":
                return await self.op_edit(request)
            if op == "redact":
                return await self.op_redact(request)
            return {"ok": False, "error": f"unknown op: {op!r}"}
        except Exception as exc:  # noqa: BLE001  # a bad request must not kill the daemon
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def room_id_for(self, room: str) -> str:
        """Turn whatever the caller typed into a room id.

        Commands hand over the argument a human wrote, which is usually an
        alias - they cannot resolve it themselves, because resolving needs
        credentials and the daemon is holding those. Watched rooms are already
        mapped, so the common case costs nothing.
        """
        if room.startswith("!"):
            return room
        for room_id, label in self.rooms.items():
            if label == room:
                return room_id
        resolved = resolve_room_alias(self.config, room)
        if resolved:
            return resolved
        raise ValueError(f"cannot resolve room {room!r}")

    async def op_send(self, request: dict) -> dict:
        body = request["body"]
        mentions = request.get("mentions")
        content = {
            "msgtype": request.get("msgtype") or "m.text",
            "body": body,
        }

        mention_block = build_mentions(mentions, room=bool(request.get("mention_room")))
        if mention_block:
            content["m.mentions"] = mention_block

        html = markdown_to_html(inject_pills(body, mentions))
        if html != body:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html
        elif request.get("formatted_body"):
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = request["formatted_body"]
        if request.get("reply_to"):
            content["m.relates_to"] = {
                "m.in_reply_to": {"event_id": request["reply_to"]}
            }
        elif request.get("thread_root"):
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": request["thread_root"],
            }

        response = await self.client.room_send(
            room_id=self.room_id_for(request["room"]),
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
        )
        return self._event_id_or_error(response)

    async def op_edit(self, request: dict) -> dict:
        """Replace an earlier message.

        Routed like the others: an edit opens the store, and a second opener
        beside the daemon is the state this whole design removes. Before this
        existed, edits went direct and produced events the daemon could not
        decrypt - holes in its own log where its corrections should be.
        """
        body = request["body"]
        content = {
            "msgtype": request.get("msgtype") or "m.text",
            "body": f"* {body}",
            "m.new_content": {
                "msgtype": request.get("msgtype") or "m.text",
                "body": body,
            },
            "m.relates_to": {
                "rel_type": "m.replace",
                "event_id": request["event_id"],
            },
        }
        response = await self.client.room_send(
            room_id=self.room_id_for(request["room"]),
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
        )
        return self._event_id_or_error(response)

    async def op_react(self, request: dict) -> dict:
        response = await self.client.room_send(
            room_id=self.room_id_for(request["room"]),
            message_type="m.reaction",
            content={
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": request["event_id"],
                    "key": request["key"],
                }
            },
            ignore_unverified_devices=True,
        )
        return self._event_id_or_error(response)

    async def op_redact(self, request: dict) -> dict:
        response = await self.client.room_redact(
            room_id=self.room_id_for(request["room"]),
            event_id=request["event_id"],
            reason=request.get("reason"),
        )
        return self._event_id_or_error(response)

    @staticmethod
    def _event_id_or_error(response) -> dict:
        event_id = getattr(response, "event_id", None)
        if event_id:
            return {"ok": True, "event_id": event_id}
        return {"ok": False, "error": str(response)}

    # -- lifecycle ---------------------------------------------------------

    async def resolve_rooms(self) -> None:
        for entry in self.config.get("watch_rooms", []):
            room_id = entry
            if entry.startswith("#"):
                room_id = resolve_room_alias(self.config, entry) or entry
            label = entry if entry.startswith("#") else room_id
            self.rooms[room_id] = label
        write_room_bundle(rooms_dir(), self.rooms)

    async def run(self) -> int:

        client_config = AsyncClientConfig(
            store_sync_tokens=True, encryption_enabled=True
        )
        self.client = AsyncClient(
            homeserver=self.config["homeserver"],
            user=self.config["user_id"],
            device_id=self.credentials["device_id"],
            store_path=str(get_store_path()),
            config=client_config,
        )
        restore_login_checked(
            self.client,
            self.config["user_id"],
            self.credentials["device_id"],
            self.credentials["access_token"],
        )
        if self.client.store:
            self.client.load_store()

        name = await self.client.get_displayname()
        self.display_name = getattr(name, "displayname", None)

        # Our own device's curve25519 key, read once. Without it every record
        # falls back to the account comparison, which cannot tell this device
        # from the human's on the same account.
        if self.client.olm:
            self.own_sender_key = self.client.olm.account.identity_keys["curve25519"]

        await self.resolve_rooms()
        self.client.add_event_callback(self.on_event, object)

        path = socket_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        server = await asyncio.start_unix_server(self.handle_client, str(path))
        os.chmod(path, 0o600)

        # One state-carrying sync before anything is served. A sync resumed from
        # a stored token returns only what is new, so nio's room list stays
        # empty - and room_send looks a room up there to decide how to encrypt.
        # Without this the first send fails with "No such room with id", which
        # names the room it was just handed.
        await self.client.sync(timeout=10000, full_state=True)
        self.last_sync = int(time.time())

        print(f"watching {len(self.rooms)} room(s), socket at {path}")

        sync_task = asyncio.create_task(self.sync_loop())
        stop_task = asyncio.create_task(self.stopping.wait())
        done, _ = await asyncio.wait(
            [sync_task, stop_task], return_when=asyncio.FIRST_COMPLETED
        )

        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()
        with contextlib.suppress(Exception):
            path.unlink()
        await self.client.close()

        for task in done:
            if task is sync_task:
                return task.result()
        sync_task.cancel()
        return 0

    async def sync_loop(self) -> int:
        """Sync until told to stop, or until the credential is gone.

        A revoked token is terminal and is announced into every log first: the
        alternative is a stream that simply stops, which reads as a quiet room.
        """
        backoff = 1
        while not self.stopping.is_set():
            try:
                response = await self.client.sync(timeout=SYNC_TIMEOUT_MS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001  # transport errors are retried
                print(f"sync error: {exc}", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            message = str(getattr(response, "message", "") or "")
            status = getattr(response, "status_code", "")
            if "M_UNKNOWN_TOKEN" in f"{status} {message}":
                self.announce(
                    "matrix-watchd stopped: the access token was rejected "
                    "(M_UNKNOWN_TOKEN). Run matrix-e2ee-setup.py to mint a new device."
                )
                print("access token rejected, stopping", file=sys.stderr)
                return 1

            self.last_sync = int(time.time())
            backoff = 1
        return 0


def run_foreground(config: dict, credentials: dict) -> int:
    # The same lock every direct command takes, held for the daemon's whole
    # run. Going through the shared helper rather than a second implementation
    # is what keeps the daemon from blocking on itself: flock is per open file
    # description, so the daemon taking it twice on two descriptors would wait
    # for a lock it already holds - which is precisely what happened when this
    # had its own copy.
    lock = store_lock(timeout=0)
    try:
        lock.__enter__()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

    pid_file = pid_file_path()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    daemon = Daemon(config, credentials)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, daemon.stopping.set)

    try:
        return loop.run_until_complete(daemon.run())
    finally:
        loop.close()
        with contextlib.suppress(Exception):
            pid_file.unlink()
        with contextlib.suppress(Exception):
            lock.__exit__(None, None, None)


def start_detached() -> int:
    existing = daemon_request({"op": "status"})
    if existing and existing.get("ok"):
        print(f"Already running (pid {existing['pid']}).")
        return 0

    process = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--foreground"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Started matrix-watchd (pid {process.pid}).")
    return 0


def stop_daemon() -> int:
    pid_file = pid_file_path()
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        print("No daemon running.")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("No daemon running (stale pid file removed).")
        with contextlib.suppress(OSError):
            pid_file.unlink()
        return 0
    print(f"Stopped matrix-watchd (pid {pid}).")
    return 0


def show_status() -> int:
    status = daemon_request({"op": "status"})
    if not status:
        print("No daemon running.")
        return 0
    print(f"pid:      {status['pid']}")
    print(f"uptime:   {status['uptime_seconds']}s")
    print(f"rooms:    {', '.join(status['rooms']) or 'none'}")
    print(f"last sync: {status['last_sync'] or 'never'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Matrix watch daemon")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--start", action="store_true", help="Start in the background")
    group.add_argument("--stop", action="store_true", help="Stop a running daemon")
    group.add_argument("--status", action="store_true", help="Ask a running daemon")
    group.add_argument("--foreground", action="store_true", help="Run in this terminal")
    args = parser.parse_args()

    prefer_ipv4()
    suppress_nio_logging()

    if args.status:
        return show_status()
    if args.stop:
        return stop_daemon()
    if args.start:
        return start_detached()

    config = load_config(require_user_id=True)
    credentials = load_credentials()
    if not credentials:
        print("No E2EE credentials. Run matrix-e2ee-setup.py first.", file=sys.stderr)
        return 1
    if not config.get("watch_rooms"):
        print(
            'No rooms to watch. Add "watch_rooms": ["#room:server"] to '
            "~/.config/matrix/config.json.",
            file=sys.stderr,
        )
        return 1
    return run_foreground(config, credentials)


if __name__ == "__main__":
    sys.exit(main())
