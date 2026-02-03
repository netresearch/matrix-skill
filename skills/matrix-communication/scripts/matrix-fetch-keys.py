#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""
Fetch missing room keys by requesting them from other devices.

When you can't decrypt old messages, this script:
1. Reads room history
2. Detects encrypted events that can't be decrypted
3. Requests keys from other verified devices
4. Syncs to receive forwarded keys
5. Saves keys to local store

Usage:
    matrix-fetch-keys.py ROOM [--limit N] [--sync-time S]
"""

import asyncio
import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lib import load_config, get_store_path, load_credentials, find_room_by_name

from nio import (
    AsyncClient,
    AsyncClientConfig,
    MegolmEvent,
    RoomMessagesResponse,
    RoomKeyRequestResponse,
    ForwardedRoomKeyEvent,
    RoomKeyEvent,
    UnknownToDeviceEvent,
)


class KeyFetcher:
    def __init__(self, client, debug=False):
        self.client = client
        self.debug = debug
        self.requested_sessions = set()
        self.received_keys = 0
        self.decryption_failures = 0

    def _debug(self, msg):
        if self.debug:
            print(f"[DEBUG] {msg}")

    async def handle_key_event(self, event):
        """Handle incoming key events."""
        if isinstance(event, (ForwardedRoomKeyEvent, RoomKeyEvent)):
            self.received_keys += 1
            room_id = getattr(event, 'room_id', 'unknown')
            session_id = getattr(event, 'session_id', 'unknown')
            print(f"  📨 Received key: {room_id[:20]}... / {session_id[:20]}...")

        elif isinstance(event, UnknownToDeviceEvent) and hasattr(event, 'source'):
            event_type = event.source.get('type', '')
            if 'room_key' in event_type.lower():
                self.received_keys += 1
                content = event.source.get('content', {})
                room_id = content.get('room_id', 'unknown')
                session_id = content.get('session_id', 'unknown')
                print(f"  📨 Received key ({event_type}): {room_id[:20]}... / {session_id[:20]}...")

    async def request_key_for_event(self, event: MegolmEvent) -> bool:
        """Request key for an undecryptable event."""
        session_key = (event.room_id, event.session_id)

        if session_key in self.requested_sessions:
            self._debug(f"Already requested: {event.session_id[:20]}")
            return False

        self.requested_sessions.add(session_key)
        self.decryption_failures += 1

        try:
            result = await self.client.request_room_key(event)
            if isinstance(result, RoomKeyRequestResponse):
                self._debug(f"Key request sent for session {event.session_id[:20]}")
                return True
            else:
                self._debug(f"Key request failed: {result}")
                return False
        except Exception as e:
            self._debug(f"Key request error: {e}")
            return False

    async def fetch_room_history(self, room_id: str, limit: int = 100):
        """Fetch room history and request keys for undecryptable events."""
        print(f"\nFetching {limit} messages from room...")

        # Get messages
        result = await self.client.room_messages(
            room_id,
            start="",  # From latest
            limit=limit,
        )

        if not isinstance(result, RoomMessagesResponse):
            print(f"Error fetching messages: {result}")
            return

        encrypted_count = 0
        decrypted_count = 0
        request_count = 0

        for event in result.chunk:
            if isinstance(event, MegolmEvent):
                encrypted_count += 1
                # This is an undecrypted event - request the key
                if await self.request_key_for_event(event):
                    request_count += 1
            elif hasattr(event, 'source') and event.source.get('type') == 'm.room.encrypted':
                # Decrypted successfully
                decrypted_count += 1

        print(f"  Messages: {len(result.chunk)}")
        print(f"  Encrypted (need keys): {encrypted_count}")
        print(f"  Decrypted (have keys): {decrypted_count}")
        print(f"  Key requests sent: {request_count}")


async def main():
    parser = argparse.ArgumentParser(description="Fetch missing room keys")
    parser.add_argument("room", help="Room name, ID, or alias")
    parser.add_argument("--limit", type=int, default=100, help="Messages to scan")
    parser.add_argument("--sync-time", type=int, default=60, help="Seconds to wait for keys")
    parser.add_argument("--debug", action="store_true", help="Debug output")
    args = parser.parse_args()

    config = load_config(require_user_id=True)
    creds = load_credentials()

    if not creds:
        print("No credentials. Run matrix-e2ee-setup.py first.", file=sys.stderr)
        return 1

    store_path = get_store_path()
    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=creds["device_id"],
        store_path=str(store_path),
        config=client_config,
    )

    fetcher = KeyFetcher(client, debug=args.debug)

    try:
        client.restore_login(config["user_id"], creds["device_id"], creds["access_token"])
        if client.store:
            client.load_store()

        # Register handlers
        client.add_to_device_callback(fetcher.handle_key_event, ForwardedRoomKeyEvent)
        client.add_to_device_callback(fetcher.handle_key_event, RoomKeyEvent)
        client.add_to_device_callback(fetcher.handle_key_event, UnknownToDeviceEvent)

        # Initial sync
        print("Initial sync...")
        await client.sync(timeout=10000)

        # Upload keys
        if client.should_upload_keys:
            await client.keys_upload()

        # Resolve room
        if args.room.startswith("!"):
            room_id = args.room
        else:
            room_id, matches = find_room_by_name(config, args.room)
            if not room_id:
                if matches:
                    print(f"Multiple matches for '{args.room}':", file=sys.stderr)
                    for m in matches:
                        print(f"  {m['name']} ({m['room_id'][:20]}...)", file=sys.stderr)
                else:
                    print(f"Could not find room: {args.room}", file=sys.stderr)
                return 1

        room = client.rooms.get(room_id)
        room_name = room.display_name if room else room_id
        print(f"Room: {room_name}")

        # Fetch history and request keys
        await fetcher.fetch_room_history(room_id, args.limit)

        if fetcher.decryption_failures == 0:
            print("\n✅ No missing keys - all messages decryptable!")
            return 0

        # Sync to receive keys
        print(f"\nWaiting {args.sync_time}s for keys from other devices...")
        print("(Ensure you have other verified devices online)")

        start_time = time.time()
        last_count = 0
        while time.time() - start_time < args.sync_time:
            await client.sync(timeout=5000)
            elapsed = int(time.time() - start_time)

            if fetcher.received_keys > last_count:
                last_count = fetcher.received_keys
            elif elapsed % 15 == 0 and elapsed > 0:
                print(f"  [{elapsed}s] Received {fetcher.received_keys} keys...")

        print(f"\n=== Results ===")
        print(f"Key requests sent: {len(fetcher.requested_sessions)}")
        print(f"Keys received: {fetcher.received_keys}")

        if fetcher.received_keys > 0:
            print(f"\n✅ Received {fetcher.received_keys} keys!")
            print("Run matrix-read-e2ee.py to read messages now.")
        else:
            print("\n⚠️  No keys received.")
            print("Possible reasons:")
            print("  - Device not verified in Element")
            print("  - Other devices offline or don't share keys")
            print("  - Try: Element → Settings → Security → enable key sharing")

    finally:
        await client.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
