#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Read recent messages from an E2EE Matrix room.

Requires libolm system library:
    Debian/Ubuntu: sudo apt install libolm-dev
    Fedora:        sudo dnf install libolm-devel
    macOS:         brew install libolm

Usage:
    matrix-read-e2ee.py ROOM [--limit N] [--json]
    matrix-read-e2ee.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)

Options:
    --limit N   Number of messages to retrieve [default: 10]
    --json      Output as JSON
    --debug     Show debug information
    --help      Show this help

Note: First run may be slow (~5-10s) for initial sync and key setup.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        RoomResolveAliasResponse,
        RoomMessageText,
        MegolmEvent,
    )
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install libolm for your platform:", file=sys.stderr)
        print("  Debian/Ubuntu: sudo apt install libolm-dev", file=sys.stderr)
        print("  Fedora:        sudo dnf install libolm-devel", file=sys.stderr)
        print("  macOS:         brew install libolm", file=sys.stderr)
        sys.exit(1)
    raise


def load_config() -> dict:
    """Load Matrix config from ~/.config/matrix/config.json"""
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    required = ["homeserver", "user_id"]
    missing = [f for f in required if f not in config]
    if missing:
        print(f"Error: Config missing required fields: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


def get_store_path() -> Path:
    """Get or create the E2EE key store directory."""
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_path = Path(xdg_data) / "matrix-skill" / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


def load_credentials() -> dict | None:
    """Load stored device credentials if they exist."""
    creds_path = get_store_path() / "credentials.json"
    if creds_path.exists():
        with open(creds_path) as f:
            return json.load(f)
    return None


def format_timestamp(ts: int) -> str:
    """Format timestamp to readable string."""
    if ts == 0:
        return "unknown"
    dt = datetime.fromtimestamp(ts / 1000)
    return dt.strftime("%Y-%m-%d %H:%M")


async def read_messages_e2ee(
    config: dict,
    room: str,
    limit: int = 10,
    debug: bool = False,
) -> list:
    """Read messages from an E2EE room."""

    store_path = get_store_path()
    stored_creds = load_credentials()

    if stored_creds and stored_creds.get("user_id") == config["user_id"]:
        device_id = stored_creds["device_id"]
        access_token = stored_creds["access_token"]
        if debug:
            print(f"Using dedicated device: {device_id}", file=sys.stderr)
    elif "access_token" in config:
        access_token = config["access_token"]
        from nio import WhoamiResponse
        temp_client = AsyncClient(config["homeserver"], config["user_id"])
        temp_client.access_token = access_token
        whoami = await temp_client.whoami()
        await temp_client.close()
        if isinstance(whoami, WhoamiResponse):
            device_id = whoami.device_id
            if debug:
                print(f"Using existing device: {device_id}", file=sys.stderr)
        else:
            return [{"error": f"Failed to get device info: {whoami}"}]
    else:
        return [{"error": "No credentials found. Run matrix-e2ee-setup.py first"}]

    client_config = AsyncClientConfig(
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    messages = []

    try:
        client.restore_login(
            user_id=config["user_id"],
            device_id=device_id,
            access_token=access_token,
        )

        if client.store:
            client.load_store()

        # Upload keys if needed
        if client.should_upload_keys:
            if debug:
                print("Uploading device keys...", file=sys.stderr)
            await client.keys_upload()

        # Resolve room alias
        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
                if debug:
                    print(f"Resolved {room} -> {room_id}", file=sys.stderr)
            else:
                return [{"error": f"Could not resolve room alias: {response}"}]

        # Sync to get messages and keys
        if debug:
            print("Syncing...", file=sys.stderr)

        # Use a filter to limit to the specific room
        sync_filter = {
            "room": {
                "rooms": [room_id],
                "timeline": {"limit": limit}
            }
        }

        await client.sync(timeout=30000, full_state=True, sync_filter=sync_filter)

        if debug:
            print(f"Sync complete. Rooms: {len(client.rooms)}", file=sys.stderr)

        # Get room
        room_obj = client.rooms.get(room_id)
        if not room_obj:
            return [{"error": f"Room not found: {room_id}"}]

        if debug:
            print(f"Room encrypted: {room_obj.encrypted}", file=sys.stderr)

        # Query keys if needed
        if client.should_query_keys:
            if debug:
                print("Querying device keys...", file=sys.stderr)
            await client.keys_query()

        # Get timeline events from the sync response
        # The room object has timeline events
        if hasattr(room_obj, 'timeline') and room_obj.timeline:
            for event in room_obj.timeline.events:
                msg = process_event(event, debug)
                if msg:
                    messages.append(msg)

        # Also check for decrypted events
        # After sync, events should be in the room's timeline
        # We need to look at the actual events from sync response

        # Get messages another way - from room_messages API
        if debug:
            print(f"Fetched {len(messages)} messages from timeline", file=sys.stderr)

        # If we didn't get messages from timeline, try room_messages
        if not messages:
            if debug:
                print("Trying room_messages API...", file=sys.stderr)
            from nio import RoomMessagesResponse
            msg_response = await client.room_messages(
                room_id=room_id,
                start="",  # From current position
                limit=limit,
            )
            if isinstance(msg_response, RoomMessagesResponse):
                for event in msg_response.chunk:
                    msg = process_event(event, debug)
                    if msg:
                        messages.append(msg)

        return messages

    finally:
        await client.close()


def process_event(event, debug=False) -> dict | None:
    """Process a timeline event into a message dict."""
    from nio import RoomMessageText, RoomMessageEmote, MegolmEvent, Event

    if debug:
        print(f"  Event type: {type(event).__name__}", file=sys.stderr)

    if isinstance(event, RoomMessageText):
        return {
            "sender": event.sender,
            "body": event.body,
            "msgtype": "m.text",
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": False,
        }
    elif isinstance(event, RoomMessageEmote):
        return {
            "sender": event.sender,
            "body": event.body,
            "msgtype": "m.emote",
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": False,
        }
    elif isinstance(event, MegolmEvent):
        # This is an encrypted event we couldn't decrypt
        return {
            "sender": event.sender,
            "body": "[Unable to decrypt]",
            "msgtype": "m.room.encrypted",
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": True,
            "session_id": event.session_id if hasattr(event, 'session_id') else None,
        }
    elif hasattr(event, 'source') and event.source.get('type') == 'm.room.message':
        # Decrypted event
        content = event.source.get('content', {})
        return {
            "sender": event.sender,
            "body": content.get('body', ''),
            "msgtype": content.get('msgtype', 'm.text'),
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": True,
        }

    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Read messages from an E2EE Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of messages (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    messages = asyncio.run(read_messages_e2ee(
        config=config,
        room=args.room,
        limit=args.limit,
        debug=args.debug,
    ))

    # Check for errors
    if messages and "error" in messages[0]:
        print(f"Error: {messages[0]['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(messages, indent=2))
    else:
        if not messages:
            print("No messages found")
            return

        for msg in messages:
            ts = format_timestamp(msg.get("timestamp", 0))
            sender = msg["sender"].split(":")[0].lstrip("@")
            body = msg["body"]
            if len(body) > 100:
                body = body[:100] + "..."
            encrypted_marker = " [E2EE]" if msg.get("encrypted") else ""
            print(f"[{ts}] {sender}{encrypted_marker}: {body}")


if __name__ == "__main__":
    main()
