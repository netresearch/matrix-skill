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
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server (resolved via directory)
                - Room name: "agent-work" (looked up from joined rooms)
    MESSAGE     Message content (markdown supported)

Options:
    --emote           Send as /me action (m.emote)
    --thread EVENT    Reply in thread (event ID of thread root)
    --reply EVENT     Reply to message (event ID to reply to)
    --no-prefix       Don't add bot_prefix from config
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help

Note: First run takes ~2-5s for initial sync and key setup.
      Subsequent runs use cached keys (~2-3s).

Examples:
    # Send by room name (easiest)
    matrix-send-e2ee.py agent-work "Hello team!"

    # Send by room ID
    matrix-send-e2ee.py '!sZBoTOreI1z0BgHY-s2ZC9MV63B1orGFigPXvYMQ22E' "Hello!"

    # Send by alias
    matrix-send-e2ee.py '#general:matrix.org' "Hello everyone!"
"""

import asyncio
import json
import sys
import os

# Add script directory to path for _lib imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    check_e2ee_dependencies,
    load_config,
    get_store_path,
    load_credentials,
    find_room_in_nio_client,
    markdown_to_html,
    add_bot_prefix,
    clean_message,
    prefer_ipv4,
    suppress_nio_logging,
)

# Check dependencies before importing nio
check_e2ee_dependencies()

from nio import (
    AsyncClient,
    AsyncClientConfig,
    RoomResolveAliasResponse,
    RoomSendResponse,
)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


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

    # Check for E2EE device credentials
    # Priority: 1) Dedicated device from setup, 2) Access token from config
    stored_creds = load_credentials()

    if stored_creds and stored_creds.get("user_id") == config["user_id"]:
        # Use dedicated E2EE device (created via matrix-e2ee-setup.py)
        device_id = stored_creds["device_id"]
        access_token = stored_creds["access_token"]
        if debug:
            print(f"Using dedicated device: {device_id}", file=sys.stderr)
    elif "access_token" in config:
        # Use access token from config (reuses existing device)
        access_token = config["access_token"]
        # Get device_id from server
        from nio import WhoamiResponse

        temp_client = AsyncClient(config["homeserver"], config["user_id"])
        temp_client.access_token = access_token
        whoami = await temp_client.whoami()
        await temp_client.close()
        if isinstance(whoami, WhoamiResponse):
            device_id = whoami.device_id
            if debug:
                print(f"Using existing device from token: {device_id}", file=sys.stderr)
        else:
            return {"error": f"Failed to get device info: {whoami}"}
    else:
        return {
            "error": "No credentials found. Add 'access_token' to config, or run matrix-e2ee-setup.py"
        }

    if debug:
        print(f"Store path: {store_path}", file=sys.stderr)

    # Configure client for E2EE
    client_config = AsyncClientConfig(
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    # Create client
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    try:
        # Restore session from stored credentials
        client.restore_login(
            user_id=config["user_id"],
            device_id=device_id,
            access_token=access_token,
        )
        if debug:
            print("Session restored", file=sys.stderr)

        if debug:
            print(f"Store initialized: {client.store is not None}", file=sys.stderr)
            print(f"Olm initialized: {client.olm is not None}", file=sys.stderr)

        # Load existing crypto keys from store
        if client.store:
            client.load_store()
            if debug:
                print(
                    f"Keys loaded. Olm account shared: {client.olm_account_shared}",
                    file=sys.stderr,
                )

        # Upload device keys if needed
        if client.should_upload_keys:
            if debug:
                print("Uploading device keys...", file=sys.stderr)
            from nio import KeysUploadResponse

            keys_response = await client.keys_upload()
            if isinstance(keys_response, KeysUploadResponse):
                if debug:
                    print("Keys uploaded successfully", file=sys.stderr)
            else:
                if debug:
                    print(f"Keys upload response: {keys_response}", file=sys.stderr)

        # Sync first to populate client.rooms (timeout=0 = no long-poll).
        if debug:
            print("Syncing (timeout=0, full_state=True)...", file=sys.stderr)

        sync_response = await client.sync(timeout=0, full_state=True)
        if (
            hasattr(sync_response, "transport_response")
            and sync_response.transport_response.status != 200
        ):
            return {"error": f"Sync failed: {sync_response}"}

        if debug:
            print(f"Sync complete. Rooms: {len(client.rooms)}", file=sys.stderr)

        # Resolve room: alias via server, name via client.rooms (post-sync)
        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
                if debug:
                    print(f"Resolved alias {room} -> {room_id}", file=sys.stderr)
            else:
                return {"error": f"Could not resolve room alias: {response}"}
        elif not room.startswith("!"):
            # Plain name — resolve from synced rooms (no HTTP calls)
            found = find_room_in_nio_client(client.rooms, room)
            if found:
                room_id = found
                if debug:
                    print(f"Found room by name: {room} -> {room_id}", file=sys.stderr)
            else:
                return {
                    "error": f"Could not find room '{room}'. Use 'matrix-rooms.py' to list available rooms."
                }

        # Get room object and check encryption
        room_obj = client.rooms.get(room_id)
        if debug:
            print(f"Room object: {room_obj is not None}", file=sys.stderr)
            if room_obj:
                print(f"Room encrypted: {room_obj.encrypted}", file=sys.stderr)
            print(f"Olm loaded: {client.olm is not None}", file=sys.stderr)

        if room_obj and room_obj.encrypted and client.olm:
            # Query device keys for all room members
            if client.should_query_keys:
                if debug:
                    print("Querying device keys...", file=sys.stderr)
                from nio import KeysQueryResponse

                keys_query_response = await client.keys_query()
                if debug:
                    if isinstance(keys_query_response, KeysQueryResponse):
                        print("Keys query successful", file=sys.stderr)
                    else:
                        print(
                            f"Keys query response: {keys_query_response}",
                            file=sys.stderr,
                        )

            # Claim one-time keys for devices we don't have sessions with
            try:
                users_to_claim = client.get_users_for_key_claiming()
                if users_to_claim:
                    if debug:
                        print(
                            f"Claiming keys for {len(users_to_claim)} users...",
                            file=sys.stderr,
                        )
                    from nio import KeysClaimResponse

                    claim_response = await client.keys_claim(users_to_claim)
                    if debug:
                        if isinstance(claim_response, KeysClaimResponse):
                            print("Keys claimed successfully", file=sys.stderr)
                        else:
                            print(
                                f"Keys claim response: {claim_response}",
                                file=sys.stderr,
                            )
            except Exception as e:
                if debug:
                    print(f"Key claiming skipped: {e}", file=sys.stderr)

            # Trust all devices in the room (TOFU - Trust On First Use)
            if debug:
                print("Room is encrypted. Trusting devices...", file=sys.stderr)
            for member_id in room_obj.users:
                try:
                    for dev_id, device in client.device_store.active_user_devices(
                        member_id
                    ):
                        if not device.verified:
                            client.verify_device(device)
                            if debug:
                                print(f"Trusted: {member_id}/{dev_id}", file=sys.stderr)
                except Exception as e:
                    if debug:
                        print(
                            f"Could not verify devices for {member_id}: {e}",
                            file=sys.stderr,
                        )

        # Build message content with HTML formatting
        content = {
            "msgtype": "m.emote" if emote else "m.text",
            "body": message,
        }

        # Add HTML formatting
        html = markdown_to_html(message)
        if html != message:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html

        # Thread reply
        if thread_id:
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": thread_id,
                "is_falling_back": True,
                "m.in_reply_to": {"event_id": reply_id or thread_id},
            }
        elif reply_id:
            content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_id}}

        # Send message (ignore unverified devices for TOFU model)
        response = await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
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
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
    parser.add_argument("message", help="Message content")
    parser.add_argument(
        "--emote", action="store_true", help="Send as /me action (m.emote msgtype)"
    )
    parser.add_argument(
        "--thread", metavar="EVENT_ID", help="Reply in thread (event ID of thread root)"
    )
    parser.add_argument(
        "--reply", metavar="EVENT_ID", help="Reply to message (event ID)"
    )
    parser.add_argument(
        "--no-prefix", action="store_true", help="Don't add bot_prefix from config"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    prefer_ipv4()
    if not args.debug:
        suppress_nio_logging()

    config = load_config(require_user_id=True)

    # Clean message from bash escaping artifacts
    message = clean_message(args.message)
    room_input = clean_message(args.room)

    # Room resolution: IDs and aliases are passed through directly.
    # Plain names are resolved AFTER sync (in the async function) using
    # client.rooms, which avoids 193 HTTP calls from find_room_by_name().
    room = room_input
    if room_input.startswith("!"):
        if args.debug:
            print(f"Using room ID directly: {room_input}", file=sys.stderr)
    elif room_input.startswith("#") and ":" not in room_input:
        # Bare alias without server part — treat as name for post-sync lookup
        room = room_input.lstrip("#")
        if args.debug:
            print(
                f"Treating '{room_input}' as room name for post-sync lookup",
                file=sys.stderr,
            )

    # Add bot prefix if configured (unless --no-prefix or emote)
    if not args.no_prefix and not args.emote and config.get("bot_prefix"):
        message = add_bot_prefix(message, config["bot_prefix"])

    # Run async send
    result = asyncio.run(
        send_message_e2ee(
            config=config,
            room=room,
            message=message,
            emote=args.emote,
            thread_id=args.thread,
            reply_id=args.reply,
            debug=args.debug,
        )
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
        print(result.get("event_id", ""))
    else:
        print(f"Message sent to {args.room}")
        print(f"Event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
