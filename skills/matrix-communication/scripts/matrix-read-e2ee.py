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
    matrix-read-e2ee.py ROOM [--limit N] [--json] [--request-keys]
    matrix-read-e2ee.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name

Options:
    --limit N            Number of messages to retrieve [default: 10]
    --request-keys       Request keys from other devices for undecryptable messages
    --json               Output as JSON
    --debug              Show debug information
    --help               Show this help

Note: First run may be slow (~5-10s) for initial sync and key setup.
      With --request-keys, wait for other devices to respond (may take 10-30s).
"""

import asyncio
import json
import sys
import os

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    load_config,
    get_store_path,
    load_credentials,
    find_room_by_name,
    format_timestamp,
    clean_message,
)

# Check dependencies before importing nio
try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        RoomResolveAliasResponse,
        RoomMessageText,
        RoomMessageEmote,
        MegolmEvent,
        RoomMessagesResponse,
    )
except ImportError as e:
    error_msg = str(e).lower()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if "olm" in error_msg:
        print("Error: libolm library not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install libolm for your platform:", file=sys.stderr)
        print("  Debian/Ubuntu: sudo apt install libolm-dev", file=sys.stderr)
        print("  Fedora:        sudo dnf install libolm-devel", file=sys.stderr)
        print("  macOS:         brew install libolm", file=sys.stderr)
    elif "nio" in error_msg or "matrix" in error_msg:
        print("Error: matrix-nio library not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install with (try in order):", file=sys.stderr)
        print("  uvx pip install 'matrix-nio[e2e]'", file=sys.stderr)
        print("  pip install 'matrix-nio[e2e]'", file=sys.stderr)
        print("  pip3 install 'matrix-nio[e2e]'", file=sys.stderr)
    else:
        print(f"Error: Missing dependency: {e}", file=sys.stderr)

    print("", file=sys.stderr)
    print("Or run the health check to diagnose and fix:", file=sys.stderr)
    print(f"  python3 {script_dir}/matrix-doctor.py --install", file=sys.stderr)
    sys.exit(1)


def process_event(event, debug=False) -> tuple[dict | None, bool]:
    """Process a timeline event into a message dict.

    Returns (message_dict, is_undecryptable)
    """
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
        }, False
    elif isinstance(event, RoomMessageEmote):
        return {
            "sender": event.sender,
            "body": event.body,
            "msgtype": "m.emote",
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": False,
        }, False
    elif isinstance(event, MegolmEvent):
        return {
            "sender": event.sender,
            "body": "[Unable to decrypt]",
            "msgtype": "m.room.encrypted",
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": True,
            "session_id": event.session_id if hasattr(event, 'session_id') else None,
        }, True
    elif hasattr(event, 'source') and event.source.get('type') == 'm.room.message':
        content = event.source.get('content', {})
        return {
            "sender": event.sender,
            "body": content.get('body', ''),
            "msgtype": content.get('msgtype', 'm.text'),
            "timestamp": event.server_timestamp,
            "event_id": event.event_id,
            "encrypted": True,
        }, False

    return None, False


async def read_messages_e2ee(
    config: dict,
    room: str,
    limit: int = 10,
    request_keys: bool = False,
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

    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    messages = []
    undecryptable_events = []

    try:
        client.restore_login(user_id=config["user_id"], device_id=device_id, access_token=access_token)

        if client.store:
            client.load_store()

        if client.should_upload_keys:
            if debug:
                print("Uploading device keys...", file=sys.stderr)
            await client.keys_upload()

        # Resolve room
        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
                if debug:
                    print(f"Resolved {room} -> {room_id}", file=sys.stderr)
            else:
                return [{"error": f"Could not resolve room alias: {response}"}]

        if debug:
            print("Syncing...", file=sys.stderr)

        sync_filter = {
            "room": {
                "rooms": [room_id],
                "timeline": {"limit": limit}
            }
        }

        await client.sync(timeout=30000, full_state=True, sync_filter=sync_filter)

        if debug:
            print(f"Sync complete. Rooms: {len(client.rooms)}", file=sys.stderr)

        room_obj = client.rooms.get(room_id)
        if not room_obj:
            return [{"error": f"Room not found: {room_id}"}]

        if debug:
            print(f"Room encrypted: {room_obj.encrypted}", file=sys.stderr)

        if client.should_query_keys:
            if debug:
                print("Querying device keys...", file=sys.stderr)
            await client.keys_query()

        if debug:
            print("Fetching messages...", file=sys.stderr)

        msg_response = await client.room_messages(room_id=room_id, start="", limit=limit)

        if isinstance(msg_response, RoomMessagesResponse):
            for event in msg_response.chunk:
                msg, is_undecryptable = process_event(event, debug)
                if msg:
                    messages.append(msg)
                    if is_undecryptable:
                        undecryptable_events.append(event)

        # Request keys for undecryptable messages
        if request_keys and undecryptable_events:
            if debug:
                print(f"\nRequesting keys for {len(undecryptable_events)} undecryptable messages...", file=sys.stderr)

            keys_requested = set()
            for event in undecryptable_events:
                if hasattr(event, 'session_id') and event.session_id not in keys_requested:
                    keys_requested.add(event.session_id)
                    try:
                        await client.request_room_key(event)
                        if debug:
                            print(f"  Requested key for session {event.session_id[:16]}...", file=sys.stderr)
                    except Exception as e:
                        if debug:
                            print(f"  Failed to request key: {e}", file=sys.stderr)

            if keys_requested:
                if debug:
                    print(f"\nWaiting for {len(keys_requested)} key(s) to arrive...", file=sys.stderr)

                for i in range(6):
                    await asyncio.sleep(5)
                    await client.sync(timeout=5000)
                    if debug:
                        print(f"  Sync {i+1}/6...", file=sys.stderr)

                if debug:
                    print("\nRetrying decryption...", file=sys.stderr)

                messages = []
                msg_response = await client.room_messages(room_id=room_id, start="", limit=limit)

                if isinstance(msg_response, RoomMessagesResponse):
                    decrypted_count = 0
                    still_encrypted = 0
                    for event in msg_response.chunk:
                        msg, is_undecryptable = process_event(event, debug)
                        if msg:
                            messages.append(msg)
                            if is_undecryptable:
                                still_encrypted += 1
                            elif msg.get("encrypted"):
                                decrypted_count += 1

                    if debug:
                        print(f"  Decrypted: {decrypted_count}, Still encrypted: {still_encrypted}", file=sys.stderr)

        return messages

    finally:
        await client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Read messages from an E2EE Matrix room")
    parser.add_argument("room", help="Room alias (#room:server), room ID (!id:server), or room name")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of messages (default: 10)")
    parser.add_argument("--request-keys", "-k", action="store_true",
                        help="Request keys from other devices for undecryptable messages")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config(require_user_id=True)

    # Clean and resolve room
    room_input = clean_message(args.room)
    room = room_input

    if not room_input.startswith("!") and not room_input.startswith("#"):
        # Room name lookup (before async)
        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room = found_id
        else:
            error_msg = f"Could not find room '{room_input}'"
            if matches:
                error_msg += f". Multiple matches found:\n"
                for m in matches:
                    alias_str = f" ({m['alias']})" if m.get("alias") else ""
                    error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
            else:
                error_msg += ". Use 'matrix-rooms.py' to list available rooms."
            print(f"Error: {error_msg}", file=sys.stderr)
            sys.exit(1)

    messages = asyncio.run(read_messages_e2ee(
        config=config,
        room=room,
        limit=args.limit,
        request_keys=args.request_keys,
        debug=args.debug,
    ))

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
