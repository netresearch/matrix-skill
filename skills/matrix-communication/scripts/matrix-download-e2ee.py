#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Download media from a Matrix room message.

Usage:
    matrix-download-e2ee.py ROOM EVENT_ID [--output DIR] [--filename NAME]
    matrix-download-e2ee.py --help

Arguments:
    ROOM        Room alias (#room:server), room ID (!id:server), or room name
    EVENT_ID    Event ID of the media message ($xxx:server)

Options:
    --output DIR     Output directory [default: .]
    --filename NAME  Override filename (default: from message body)
    --debug          Show debug information
    --help           Show this help
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _lib import (
    check_e2ee_dependencies,
    load_config,
    get_store_path,
    load_credentials,
    find_room_in_nio_client,
    prefer_ipv4,
    suppress_nio_logging,
)

check_e2ee_dependencies()

from nio import (
    AsyncClient,
    AsyncClientConfig,
    RoomResolveAliasResponse,
    RoomGetEventError,
    DownloadError,
    MemoryDownloadResponse,
)


async def download_media(
    config: dict,
    room: str,
    event_id: str,
    output_dir: str = ".",
    filename: str | None = None,
    debug: bool = False,
) -> str:
    """Download media from a Matrix message event."""
    store_path = get_store_path()
    stored_creds = load_credentials()

    if stored_creds and stored_creds.get("user_id") == config["user_id"]:
        device_id = stored_creds["device_id"]
        access_token = stored_creds["access_token"]
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
            raise RuntimeError(f"Failed to get device info: {whoami}")
    else:
        raise RuntimeError("No credentials found. Run matrix-e2ee-setup.py first.")

    client_config = AsyncClientConfig(store_sync_tokens=True, encryption_enabled=True)
    client = AsyncClient(
        homeserver=config["homeserver"],
        user=config["user_id"],
        device_id=device_id,
        store_path=str(store_path),
        config=client_config,
    )

    try:
        client.restore_login(
            user_id=config["user_id"], device_id=device_id, access_token=access_token
        )

        if client.store:
            client.load_store()

        if client.should_upload_keys:
            await client.keys_upload()

        # Sync to get room keys
        if debug:
            print("Syncing...", file=sys.stderr)
        await client.sync(timeout=0, full_state=True)

        # Resolve room
        room_id = room
        if room.startswith("#"):
            response = await client.room_resolve_alias(room)
            if isinstance(response, RoomResolveAliasResponse):
                room_id = response.room_id
            else:
                raise RuntimeError(f"Could not resolve room alias: {response}")
        elif not room.startswith("!"):
            found = find_room_in_nio_client(client.rooms, room)
            if found:
                room_id = found
            else:
                raise RuntimeError(
                    f"Could not find room '{room}'. Use 'matrix-rooms.py' to list rooms."
                )

        # Fetch the event
        if debug:
            print(f"Fetching event {event_id}...", file=sys.stderr)

        resp = await client.room_get_event(room_id, event_id)
        if isinstance(resp, RoomGetEventError):
            raise RuntimeError(f"Failed to get event: {resp.message}")

        event = resp.event
        source = event.source if hasattr(event, "source") else {}
        content = source.get("content", {})
        msgtype = content.get("msgtype", "")

        if msgtype not in ("m.image", "m.file", "m.video", "m.audio"):
            raise RuntimeError(f"Event is not a media message (msgtype: {msgtype})")

        # Get mxc URL
        if "file" in content:
            mxc_url = content["file"]["url"]
        elif "url" in content:
            mxc_url = content["url"]
        else:
            raise RuntimeError("No media URL found in event")

        if debug:
            print(f"Downloading {mxc_url}...", file=sys.stderr)

        # Determine filename — sanitize to prevent path traversal
        if not filename:
            raw_name = content.get("body", "media_download")
            filename = Path(raw_name).name  # Strip directory components
        else:
            filename = Path(filename).name

        # Download media into memory (don't pass filename to avoid unnecessary disk write)
        resp = await client.download(mxc=mxc_url)

        if isinstance(resp, DownloadError):
            raise RuntimeError(f"Download failed: {resp.message}")

        # Get raw bytes
        if isinstance(resp, MemoryDownloadResponse):
            data = resp.body
        else:
            data = Path(resp.filename).read_bytes()

        # Decrypt E2EE media if encrypted
        if "file" in content:
            from nio.crypto import decrypt_attachment

            file_info = content["file"]
            data = decrypt_attachment(
                ciphertext=data,
                key=file_info["key"]["k"],
                hash=file_info["hashes"]["sha256"],
                iv=file_info["iv"],
            )

        # Save to file
        out_path = Path(output_dir) / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)

        if debug:
            print(
                f"Saved to {out_path} ({out_path.stat().st_size:,} bytes)",
                file=sys.stderr,
            )

        return str(out_path)

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Download media from Matrix room")
    parser.add_argument("room", help="Room alias, ID, or name")
    parser.add_argument("event_id", help="Event ID of the media message")
    parser.add_argument("--output", default=".", help="Output directory [default: .]")
    parser.add_argument("--filename", help="Override filename")
    parser.add_argument("--debug", action="store_true", help="Debug output")
    args = parser.parse_args()

    suppress_nio_logging()
    prefer_ipv4()

    config = load_config()

    try:
        path = asyncio.run(
            download_media(
                config,
                args.room,
                args.event_id,
                output_dir=args.output,
                filename=args.filename,
                debug=args.debug,
            )
        )
        print(path)
    except Exception as e:
        if args.debug:
            raise
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
