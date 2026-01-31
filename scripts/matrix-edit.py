#!/usr/bin/env python3
"""Edit an existing message in a Matrix room.

Usage:
    matrix-edit.py ROOM EVENT_ID NEW_MESSAGE
    matrix-edit.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)
    EVENT_ID    Event ID of the message to edit ($xxx:server)
    NEW_MESSAGE The new message content (replaces original)

Options:
    --json      Output as JSON
    --quiet     Minimal output
    --debug     Show debug information
    --help      Show this help
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path


def load_config() -> dict:
    """Load Matrix config from ~/.config/matrix/config.json"""
    config_path = Path.home() / ".config" / "matrix" / "config.json"
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # Add bot_prefix handling
    return config


def matrix_request(config: dict, method: str, endpoint: str, data: dict = None) -> dict:
    """Make a Matrix API request."""
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json"
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            return {"error": error_json.get("error", error_body), "errcode": error_json.get("errcode")}
        except:
            return {"error": error_body, "errcode": str(e.code)}


def resolve_room_alias(config: dict, alias: str) -> str:
    """Resolve a room alias to room ID."""
    encoded_alias = urllib.parse.quote(alias, safe='')
    result = matrix_request(config, "GET", f"/directory/room/{encoded_alias}")
    if "room_id" in result:
        return result["room_id"]
    raise ValueError(f"Could not resolve room alias: {result.get('error', 'Unknown error')}")


def shorten_service_urls(text: str) -> str:
    """Convert service URLs to shorter linked text."""
    text = re.sub(
        r'https?://[^/]+/browse/([A-Z][A-Z0-9]+-\d+)',
        r'[\1](https://\g<0>)',
        text
    )
    text = re.sub(r'\(https://https?://', r'(https://', text)
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)',
        r'[\1/\2#\4](\g<0>)',
        text
    )
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/commit/([a-f0-9]{7,40})',
        r'[\1/\2@\3](\g<0>)',
        text
    )
    text = re.sub(
        r'https?://[^/]+/([^/]+/[^/]+)/-/(issues|merge_requests)/(\d+)',
        r'[\1#\3](\g<0>)',
        text
    )
    return text


def markdown_to_html(text: str) -> str:
    """Convert markdown to Matrix HTML."""
    html = shorten_service_urls(text)

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
    html = re.sub(r'\|\|(.+?)\|\|', r'<span data-mx-spoiler>\1</span>', html)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(
        r'(?<!["\'/])(@[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )
    html = re.sub(
        r'(?<!["\'/])(#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )
    html = re.sub(r'~~(.+?)~~', r'<del>\1</del>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
    html = re.sub(r'\n{2,}', '\n', html)

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


def clean_message(message: str) -> str:
    """Clean message from bash escaping artifacts."""
    return message.replace('\\!', '!')


def edit_message(config: dict, room_id: str, event_id: str, new_message: str) -> dict:
    """Edit an existing message in a Matrix room."""
    txn_id = str(int(time.time() * 1000))

    # Build the replacement content
    content = {
        "msgtype": "m.text",
        "body": f"* {new_message}",  # Prefix with * for fallback
        "m.new_content": {
            "msgtype": "m.text",
            "body": new_message,
        },
        "m.relates_to": {
            "rel_type": "m.replace",
            "event_id": event_id,
        }
    }

    # Add HTML formatting
    html = markdown_to_html(new_message)
    if html != new_message:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = f"* {html}"
        content["m.new_content"]["format"] = "org.matrix.custom.html"
        content["m.new_content"]["formatted_body"] = html

    return matrix_request(
        config,
        "PUT",
        f"/rooms/{urllib.parse.quote(room_id, safe='')}/send/m.room.message/{txn_id}",
        content
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Edit a message in a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("event_id", help="Event ID of the message to edit")
    parser.add_argument("message", help="New message content")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--debug", action="store_true", help="Show debug info")

    args = parser.parse_args()

    config = load_config()

    # Clean message
    message = clean_message(args.message)

    # Resolve room alias if needed
    room_id = args.room
    if args.room.startswith("#"):
        try:
            room_id = resolve_room_alias(config, args.room)
            if args.debug:
                print(f"Resolved {args.room} -> {room_id}", file=sys.stderr)
        except ValueError as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Edit message
    result = edit_message(config, room_id, args.event_id, message)

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
