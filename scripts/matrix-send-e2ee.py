#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Send an E2EE-capable message to a Matrix room.

Requires libolm system library:
    Debian/Ubuntu: sudo apt install libolm-dev
    Fedora:        sudo dnf install libolm-devel
    macOS:         brew install libolm

Usage:
    matrix-send-e2ee.py ROOM MESSAGE [OPTIONS]
    matrix-send-e2ee.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)
    MESSAGE     Message content (markdown supported)

Options:
    --emote           Send as /me action (m.emote)
    --thread EVENT    Reply in thread (event ID of thread root)
    --reply EVENT     Reply to message (event ID to reply to)
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help

Note: First run may be slow (~5-10s) for initial sync and key setup.
      Subsequent runs use cached keys and are faster.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Check for libolm before importing nio
try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        RoomResolveAliasResponse,
        RoomSendResponse,
        LoginResponse,
    )
    from nio.store import SqliteStore
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install libolm for your platform:", file=sys.stderr)
        print("  Debian/Ubuntu: sudo apt install libolm-dev", file=sys.stderr)
        print("  Fedora:        sudo dnf install libolm-devel", file=sys.stderr)
        print("  macOS:         brew install libolm", file=sys.stderr)
        print("", file=sys.stderr)
        print("Then run this script again.", file=sys.stderr)
        sys.exit(1)
    raise


def load_config() -> dict:
    """Load Matrix config from ~/.config/matrix/config.json"""
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print("Create it with:", file=sys.stderr)
        print(json.dumps({
            "homeserver": "https://matrix.org",
            "access_token": "syt_...",
            "user_id": "@user:matrix.org",
            "device_id": "DEVICEID"
        }, indent=2), file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # Validate required fields for E2EE
    required = ["homeserver", "access_token", "user_id"]
    missing = [f for f in required if f not in config]
    if missing:
        print(f"Error: Config missing required fields: {', '.join(missing)}", file=sys.stderr)
        print("E2EE requires: homeserver, access_token, user_id", file=sys.stderr)
        print("Optional: device_id (will be auto-generated if missing)", file=sys.stderr)
        sys.exit(1)

    return config


def get_store_path() -> Path:
    """Get or create the E2EE key store directory."""
    # Use XDG_DATA_HOME or default to ~/.local/share
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_path = Path(xdg_data) / "matrix-skill" / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


async def send_message_e2ee(
    config: dict,
    room: str,
    message: str,
    emote: bool = False,
    thread_id: str = None,
    reply_id: str = None,
    debug: bool = False,
) -> dict:
    """Send an E2EE-capable message to a Matrix room."""

    store_path = get_store_path()

    # Configure client for E2EE
    client_config = AsyncClientConfig(
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=config.get("device_id"),
        store_path=str(store_path),
        config=client_config,
    )

    try:
        # Set access token directly (no password login needed)
        client.access_token = config["access_token"]
        client.user_id = config["user_id"]

        if debug:
            print(f"Store path: {store_path}", file=sys.stderr)

        # Check if we have an existing device_id in config or need to get one
        if not client.device_id:
            # Get device_id from whoami endpoint
            from nio import WhoamiResponse
            whoami = await client.whoami()
            if isinstance(whoami, WhoamiResponse):
                client.device_id = whoami.device_id
                if debug:
                    print(f"Got device ID from server: {client.device_id}", file=sys.stderr)
            else:
                return {"error": f"Failed to get device info: {whoami}"}

        if debug:
            print(f"Device ID: {client.device_id}", file=sys.stderr)

        # Load existing keys from store if available
        if client.store:
            client.load_store()

        # Resolve room alias if needed
        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
                if debug:
                    print(f"Resolved {room} -> {room_id}", file=sys.stderr)
            else:
                return {"error": f"Could not resolve room alias: {response}"}

        # Sync to get device keys (required for E2EE)
        if debug:
            print("Syncing to fetch device keys...", file=sys.stderr)

        sync_response = await client.sync(timeout=30000, full_state=True)
        if hasattr(sync_response, "transport_response") and sync_response.transport_response.status != 200:
            return {"error": f"Sync failed: {sync_response}"}

        if debug:
            print(f"Sync complete. Rooms: {len(client.rooms)}", file=sys.stderr)

        # Trust all devices in the room (TOFU - Trust On First Use)
        room_obj = client.rooms.get(room_id)
        if room_obj and room_obj.encrypted and client.olm:
            if debug:
                print(f"Room is encrypted. Trusting devices...", file=sys.stderr)
            for member_id in room_obj.users:
                try:
                    for device_id, device in client.device_store.active_user_devices(member_id):
                        if not device.verified:
                            client.verify_device(device)
                            if debug:
                                print(f"Trusted: {member_id}/{device_id}", file=sys.stderr)
                except Exception as e:
                    if debug:
                        print(f"Could not verify devices for {member_id}: {e}", file=sys.stderr)

        # Build message content
        content = {
            "msgtype": "m.emote" if emote else "m.text",
            "body": message,
        }

        # Thread reply
        if thread_id:
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": thread_id,
                "is_falling_back": True,
                "m.in_reply_to": {"event_id": reply_id or thread_id},
            }
        elif reply_id:
            content["m.relates_to"] = {
                "m.in_reply_to": {"event_id": reply_id}
            }

        # Send message
        response = await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
        )

        if isinstance(response, RoomSendResponse):
            return {"event_id": response.event_id, "room_id": room_id}
        else:
            return {"error": str(response)}

    finally:
        await client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Send an E2EE-capable message to a Matrix room"
    )
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("message", help="Message content")
    parser.add_argument("--emote", action="store_true",
                        help="Send as /me action (m.emote msgtype)")
    parser.add_argument("--thread", metavar="EVENT_ID",
                        help="Reply in thread (event ID of thread root)")
    parser.add_argument("--reply", metavar="EVENT_ID",
                        help="Reply to message (event ID)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Run async send
    result = asyncio.run(send_message_e2ee(
        config=config,
        room=args.room,
        message=args.message,
        emote=args.emote,
        thread_id=args.thread,
        reply_id=args.reply,
        debug=args.debug,
    ))

    if "error" in result:
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result))
    elif args.quiet:
        print(result.get("event_id", ""))
    else:
        print(f"Message sent to {args.room}")
        print(f"Event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
