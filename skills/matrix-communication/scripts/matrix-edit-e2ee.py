#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Edit an existing message in an E2EE Matrix room.

Usage:
    matrix-edit-e2ee.py ROOM EVENT_ID NEW_MESSAGE
    matrix-edit-e2ee.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name
    EVENT_ID    Event ID of the message to edit ($xxx:server)
    NEW_MESSAGE The new message content (replaces original)

Options:
    --no-prefix Don't add bot_prefix from config
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help
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
    markdown_to_html,
    add_bot_prefix,
    clean_message,
)

try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        RoomResolveAliasResponse,
        RoomSendResponse,
    )
except ImportError as e:
    if "olm" in str(e).lower():
        print("Error: libolm library not found.", file=sys.stderr)
        sys.exit(1)
    raise


async def edit_message_e2ee(config: dict, room: str, event_id: str, message: str, debug: bool = False) -> dict:
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
        else:
            return {"error": f"Failed to get device info: {whoami}"}
    else:
        return {"error": "No credentials found. Run matrix-e2ee-setup.py first"}

    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    try:
        client.restore_login(user_id=config["user_id"], device_id=device_id, access_token=access_token)
        if client.store:
            client.load_store()
        if client.should_upload_keys:
            await client.keys_upload()

        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
            else:
                return {"error": f"Could not resolve room alias: {response}"}

        await client.sync(timeout=30000, full_state=True)

        room_obj = client.rooms.get(room_id)
        if room_obj and room_obj.encrypted and client.olm:
            if client.should_query_keys:
                await client.keys_query()
            for member_id in room_obj.users:
                try:
                    for dev_id, device in client.device_store.active_user_devices(member_id):
                        if not device.verified:
                            client.verify_device(device)
                except:
                    pass

        # Build edit content
        content = {
            "msgtype": "m.text",
            "body": f"* {message}",
            "m.new_content": {"msgtype": "m.text", "body": message},
            "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
        }
        html = markdown_to_html(message)
        if html != message:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = f"* {html}"
            content["m.new_content"]["format"] = "org.matrix.custom.html"
            content["m.new_content"]["formatted_body"] = html

        response = await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
        )

        if isinstance(response, RoomSendResponse):
            return {"event_id": response.event_id, "room_id": room_id}
        return {"error": str(response)}
    finally:
        await client.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Edit a message in an E2EE Matrix room")
    parser.add_argument("room", help="Room alias (#room:server), room ID (!id:server), or room name")
    parser.add_argument("event_id", help="Event ID to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument("--no-prefix", action="store_true", help="Don't add bot_prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")
    args = parser.parse_args()

    config = load_config(require_user_id=True)
    message = clean_message(args.message)
    room_input = clean_message(args.room)

    if not args.no_prefix and config.get("bot_prefix"):
        message = add_bot_prefix(message, config["bot_prefix"])

    # Resolve room name if needed
    room = room_input
    if not room_input.startswith("!") and not room_input.startswith("#"):
        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room = found_id
            if args.debug:
                print(f"Found room: {room}", file=sys.stderr)
        else:
            error_msg = f"Could not find room '{room_input}'"
            if matches:
                error_msg += f". Multiple matches found:\n"
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

    result = asyncio.run(edit_message_e2ee(config, room, args.event_id, message, args.debug))

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
        print(f"Message edited in {args.room}")
        print(f"Edit event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
