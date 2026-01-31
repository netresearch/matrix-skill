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
import re
import sys
from pathlib import Path

# Check for libolm before importing nio
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
            "user_id": "@user:matrix.org"
        }, indent=2), file=sys.stderr)
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


def get_credentials_path() -> Path:
    """Get path for stored E2EE device credentials."""
    return get_store_path() / "credentials.json"


def load_credentials() -> dict | None:
    """Load stored device credentials if they exist."""
    creds_path = get_credentials_path()
    if creds_path.exists():
        with open(creds_path) as f:
            return json.load(f)
    return None


def shorten_service_urls(text: str) -> str:
    """Convert service URLs to shorter linked text."""
    # Jira URLs
    text = re.sub(
        r'https?://[^/]+/browse/([A-Z][A-Z0-9]+-\d+)',
        r'[\1](https://\g<0>)',
        text
    )
    text = re.sub(r'\(https://https?://', r'(https://', text)

    # GitHub Issues/PRs
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)',
        r'[\1/\2#\4](\g<0>)',
        text
    )

    # GitHub commits
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/commit/([a-f0-9]{7,40})',
        r'[\1/\2@\3](\g<0>)',
        text
    )

    # GitLab Issues/MRs
    text = re.sub(
        r'https?://[^/]+/([^/]+/[^/]+)/-/(issues|merge_requests)/(\d+)',
        r'[\1#\3](\g<0>)',
        text
    )

    return text


def markdown_to_html(text: str) -> str:
    """Convert markdown to Matrix HTML."""
    html = shorten_service_urls(text)

    # Extract and protect code blocks
    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        idx = len(code_blocks)
        if lang:
            code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
        else:
            code_blocks.append(f'<pre><code>{code}</code></pre>')
        return f'{{{{CODEBLOCK_{idx}}}}}'

    html = re.sub(r'```(\w*)\n(.*?)```', save_code_block, html, flags=re.DOTALL)

    # Spoilers
    html = re.sub(r'\|\|(.+?)\|\|', r'<span data-mx-spoiler>\1</span>', html)

    # Markdown links
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    # Matrix mentions
    html = re.sub(
        r'(?<!["\'/])(@[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )

    # Room links
    html = re.sub(
        r'(?<!["\'/])(#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )

    # Strikethrough, bold, italic, code
    html = re.sub(r'~~(.+?)~~', r'<del>\1</del>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)

    # Normalize newlines
    html = re.sub(r'\n{2,}', '\n', html)

    # Process lists and blockquotes
    lines = html.split('\n')
    in_list = False
    in_quote = False
    result = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('> '):
            if not in_quote:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append('<blockquote>')
                in_quote = True
            result.append(stripped[2:])
        elif stripped.startswith('- '):
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append(f'<li>{stripped[2:]}</li>')
        elif stripped == '':
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            continue
        else:
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            if in_list:
                result.append('</ul>')
                in_list = False
            result.append(line)

    if in_quote:
        result.append('</blockquote>')
    if in_list:
        result.append('</ul>')

    html = '{{BR}}'.join(result)
    html = re.sub(r'\{\{BR\}\}(?=<ul>|<li>|</ul>|</li>|<blockquote>|</blockquote>|<pre>)', '', html)
    html = re.sub(r'(</ul>|</li>|</blockquote>|</pre>)\{\{BR\}\}', r'\1', html)
    html = re.sub(r'(<blockquote>)\{\{BR\}\}', r'\1', html)
    html = html.replace('{{BR}}', '<br>')

    for idx, block in enumerate(code_blocks):
        html = html.replace(f'{{{{CODEBLOCK_{idx}}}}}', block)

    return html


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
            print(f"Session restored", file=sys.stderr)

        if debug:
            print(f"Store initialized: {client.store is not None}", file=sys.stderr)
            print(f"Olm initialized: {client.olm is not None}", file=sys.stderr)

        # Load existing crypto keys from store
        if client.store:
            client.load_store()
            if debug:
                print(f"Keys loaded. Olm account shared: {client.olm_account_shared}", file=sys.stderr)

        # Upload device keys if needed
        if client.should_upload_keys:
            if debug:
                print("Uploading device keys...", file=sys.stderr)
            from nio import KeysUploadResponse
            keys_response = await client.keys_upload()
            if isinstance(keys_response, KeysUploadResponse):
                if debug:
                    print(f"Keys uploaded successfully", file=sys.stderr)
            else:
                if debug:
                    print(f"Keys upload response: {keys_response}", file=sys.stderr)

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
                        print(f"Keys query successful", file=sys.stderr)
                    else:
                        print(f"Keys query response: {keys_query_response}", file=sys.stderr)

            # Claim one-time keys for devices we don't have sessions with
            try:
                users_to_claim = client.get_users_for_key_claiming()
                if users_to_claim:
                    if debug:
                        print(f"Claiming keys for {len(users_to_claim)} users...", file=sys.stderr)
                    from nio import KeysClaimResponse
                    claim_response = await client.keys_claim(users_to_claim)
                    if debug:
                        if isinstance(claim_response, KeysClaimResponse):
                            print(f"Keys claimed successfully", file=sys.stderr)
                        else:
                            print(f"Keys claim response: {claim_response}", file=sys.stderr)
            except Exception as e:
                if debug:
                    print(f"Key claiming skipped: {e}", file=sys.stderr)

            # Trust all devices in the room (TOFU - Trust On First Use)
            if debug:
                print(f"Room is encrypted. Trusting devices...", file=sys.stderr)
            for member_id in room_obj.users:
                try:
                    for dev_id, device in client.device_store.active_user_devices(member_id):
                        if not device.verified:
                            client.verify_device(device)
                            if debug:
                                print(f"Trusted: {member_id}/{dev_id}", file=sys.stderr)
                except Exception as e:
                    if debug:
                        print(f"Could not verify devices for {member_id}: {e}", file=sys.stderr)

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
            content["m.relates_to"] = {
                "m.in_reply_to": {"event_id": reply_id}
            }

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


def clean_message(message: str) -> str:
    """Clean message from bash escaping artifacts.

    Bash history expansion in interactive shells can escape ! to \!
    when using double quotes. This removes those artifacts.
    """
    # Remove backslash before ! (bash history expansion artifact)
    return message.replace('\\!', '!')


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
    parser.add_argument("--no-prefix", action="store_true",
                        help="Don't add bot_prefix from config")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Clean message from bash escaping artifacts
    message = clean_message(args.message)

    # Add bot prefix if configured (unless --no-prefix or emote)
    if not args.no_prefix and not args.emote and config.get("bot_prefix"):
        message = f"{config['bot_prefix']} {message}"

    # Run async send
    result = asyncio.run(send_message_e2ee(
        config=config,
        room=args.room,
        message=message,
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
