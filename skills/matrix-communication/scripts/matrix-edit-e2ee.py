#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matrix-nio[e2e]"]
# ///
"""Edit an existing message in an E2EE Matrix room.

Usage:
    matrix-edit-e2ee.py ROOM EVENT_ID NEW_MESSAGE
    matrix-edit-e2ee.py --help
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

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


def load_config() -> dict:
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def get_store_path() -> Path:
    xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    store_path = Path(xdg_data) / "matrix-skill" / "store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


def load_credentials() -> dict | None:
    creds_path = get_store_path() / "credentials.json"
    if creds_path.exists():
        with open(creds_path) as f:
            return json.load(f)
    return None


def clean_message(message: str) -> str:
    return message.replace('\\!', '!')


def shorten_service_urls(text: str) -> str:
    text = re.sub(r'https?://[^/]+/browse/([A-Z][A-Z0-9]+-\d+)', r'[\1](https://\g<0>)', text)
    text = re.sub(r'\(https://https?://', r'(https://', text)
    text = re.sub(r'https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)', r'[\1/\2#\4](\g<0>)', text)
    text = re.sub(r'https?://github\.com/([^/]+)/([^/]+)/commit/([a-f0-9]{7,40})', r'[\1/\2@\3](\g<0>)', text)
    text = re.sub(r'https?://[^/]+/([^/]+/[^/]+)/-/(issues|merge_requests)/(\d+)', r'[\1#\3](\g<0>)', text)
    return text


def markdown_to_html(text: str) -> str:
    html = shorten_service_urls(text)
    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        idx = len(code_blocks)
        code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>' if lang else f'<pre><code>{code}</code></pre>')
        return f'{{{{CODEBLOCK_{idx}}}}}'
    html = re.sub(r'```(\w*)\n(.*?)```', save_code_block, html, flags=re.DOTALL)
    html = re.sub(r'(?<!\|)\|\|(.+?)\|\|(?!\|)', r'<span data-mx-spoiler>\1</span>', html)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(r'(?<!["\'/])(@[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'<a href="https://matrix.to/#/\1">\1</a>', html)
    html = re.sub(r'(?<!["\'/])(#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'<a href="https://matrix.to/#/\1">\1</a>', html)
    html = re.sub(r'~~(.+?)~~', r'<del>\1</del>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
    html = re.sub(r'\n{2,}', '\n', html)

    lines = html.split('\n')
    in_list = in_quote = in_table = False
    result = []
    for line in lines:
        stripped = line.strip()

        # Headings
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            if in_quote: result.append('</blockquote>'); in_quote = False
            if in_list: result.append('</ul>'); in_list = False
            if in_table: result.append('</table>'); in_table = False
            level = len(heading_match.group(1))
            result.append(f'<h{level}>{heading_match.group(2)}</h{level}>')
            continue

        # Tables
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if all(re.match(r'^[-:]+$', c) for c in cells if c): continue
            if in_quote: result.append('</blockquote>'); in_quote = False
            if in_list: result.append('</ul>'); in_list = False
            if not in_table:
                result.append('<table>'); in_table = True
                result.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
            else:
                result.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            continue

        if in_table: result.append('</table>'); in_table = False

        if stripped.startswith('> '):
            if not in_quote:
                if in_list: result.append('</ul>'); in_list = False
                result.append('<blockquote>'); in_quote = True
            result.append(stripped[2:])
        elif stripped.startswith('- '):
            if in_quote: result.append('</blockquote>'); in_quote = False
            if not in_list: result.append('<ul>'); in_list = True
            result.append(f'<li>{stripped[2:]}</li>')
        elif stripped == '':
            if in_quote: result.append('</blockquote>'); in_quote = False
        else:
            if in_quote: result.append('</blockquote>'); in_quote = False
            if in_list: result.append('</ul>'); in_list = False
            result.append(line)
    if in_quote: result.append('</blockquote>')
    if in_list: result.append('</ul>')
    if in_table: result.append('</table>')

    html = '{{BR}}'.join(result)
    html = re.sub(r'\{\{BR\}\}(?=<ul>|<li>|</ul>|</li>|<blockquote>|</blockquote>|<pre>|<table>|<tr>|</table>|<h[1-6]>)', '', html)
    html = re.sub(r'(</ul>|</li>|</blockquote>|</pre>|</table>|</tr>|</h[1-6]>)\{\{BR\}\}', r'\1', html)
    html = re.sub(r'(<blockquote>|<table>)\{\{BR\}\}', r'\1', html)
    html = html.replace('{{BR}}', '<br>')
    for idx, block in enumerate(code_blocks):
        html = html.replace(f'{{{{CODEBLOCK_{idx}}}}}', block)
    return html


def add_bot_prefix(message: str, prefix: str) -> str:
    """Add bot prefix intelligently - after heading if present, else at start."""
    lines = message.split('\n')
    if not lines: return f"{prefix} {message}"
    first_line = lines[0].strip()
    if re.match(r'^#{1,6}\s+', first_line):
        lines[0] = first_line
        if len(lines) > 1:
            lines.insert(1, f"\n{prefix}")
        else:
            lines.append(f"\n{prefix}")
        return '\n'.join(lines)
    return f"{prefix} {message}"


async def edit_message_e2ee(config: dict, room: str, event_id: str, message: str, debug: bool = False) -> dict:
    store_path = get_store_path()
    stored_creds = load_credentials()

    if stored_creds and stored_creds.get("user_id") == config["user_id"]:
        device_id = stored_creds["device_id"]
        access_token = stored_creds["access_token"]
        if debug: print(f"Using dedicated device: {device_id}", file=sys.stderr)
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
        if client.store: client.load_store()
        if client.should_upload_keys: await client.keys_upload()

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
            if client.should_query_keys: await client.keys_query()
            for member_id in room_obj.users:
                try:
                    for dev_id, device in client.device_store.active_user_devices(member_id):
                        if not device.verified: client.verify_device(device)
                except: pass

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
    parser.add_argument("room", help="Room alias or ID")
    parser.add_argument("event_id", help="Event ID to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument("--no-prefix", action="store_true", help="Don't add bot_prefix")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")
    args = parser.parse_args()

    config = load_config()
    message = clean_message(args.message)
    room = clean_message(args.room)  # Room IDs also start with ! and need cleaning
    if not args.no_prefix and config.get("bot_prefix"):
        message = add_bot_prefix(message, config["bot_prefix"])

    result = asyncio.run(edit_message_e2ee(config, room, args.event_id, message, args.debug))

    if "error" in result:
        if args.json: print(json.dumps(result))
        else: print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json: print(json.dumps(result))
    elif args.quiet: print(result.get("event_id", ""))
    else: print(f"Message edited in {args.room}\nEdit event ID: {result.get('event_id')}")


if __name__ == "__main__":
    main()
