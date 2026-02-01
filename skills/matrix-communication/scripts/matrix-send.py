#!/usr/bin/env python3
"""Send a message to a Matrix room.

Usage:
    matrix-send.py ROOM MESSAGE [OPTIONS]
    matrix-send.py --help

Arguments:
    ROOM        Room alias (#room:server) or room ID (!id:server)
    MESSAGE     Message content (markdown supported)

Options:
    --format FORMAT   Message format: text or markdown [default: markdown]
    --emote           Send as /me action (m.emote)
    --thread EVENT    Reply in thread (event ID of thread root)
    --reply EVENT     Reply to message (event ID to reply to)
    --json            Output as JSON
    --quiet           Minimal output
    --debug           Show debug information
    --help            Show this help

Effects (Element clients):
    Include emoji in message to trigger visual effects:
    🎉 or 🎊 = confetti, 🎆 = fireworks, ❄️ = snowfall
"""

import json
import os
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
        print("Create it with:", file=sys.stderr)
        print(json.dumps({
            "homeserver": "https://matrix.org",
            "access_token": "syt_..."
        }, indent=2), file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def matrix_request(config: dict, method: str, endpoint: str, data: dict = None) -> dict:
    """Make a Matrix API request."""
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json"
    }

    body = json.dumps(data).encode() if data is not None else None
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
    """Convert service URLs to shorter linked text.

    Supported services:
    - Jira: https://jira.example.com/browse/PROJ-123 -> [PROJ-123](url)
    - GitHub Issues/PRs: https://github.com/owner/repo/issues/123 -> [owner/repo#123](url)
    - GitHub commits: https://github.com/owner/repo/commit/abc123 -> [owner/repo@abc123](url)
    - GitLab Issues/MRs: https://gitlab.example.com/group/project/-/issues/123 -> [group/project#123](url)
    """
    # Jira URLs: https://jira.*/browse/PROJ-123 or https://*.atlassian.net/browse/PROJ-123
    text = re.sub(
        r'https?://[^/]+/browse/([A-Z][A-Z0-9]+-\d+)',
        r'[\1](https://\g<0>)',
        text
    )
    # Fix double https
    text = re.sub(r'\(https://https?://', r'(https://', text)

    # GitHub Issues/PRs: https://github.com/owner/repo/issues/123 or /pull/123
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)',
        r'[\1/\2#\4](\g<0>)',
        text
    )

    # GitHub commits: https://github.com/owner/repo/commit/abc123...
    text = re.sub(
        r'https?://github\.com/([^/]+)/([^/]+)/commit/([a-f0-9]{7,40})',
        r'[\1/\2@\3](\g<0>)',
        text
    )

    # GitLab Issues/MRs: https://gitlab.*/group/project/-/issues/123 or /-/merge_requests/123
    text = re.sub(
        r'https?://[^/]+/([^/]+/[^/]+)/-/(issues|merge_requests)/(\d+)',
        r'[\1#\3](\g<0>)',
        text
    )

    return text


def markdown_to_html(text: str) -> str:
    """Convert markdown to Matrix HTML with smart features.

    Supports:
    - ## headings (h1-h6)
    - **bold**, *italic*, `code`, ~~strikethrough~~
    - [text](url) links
    - ||spoiler|| text (Discord-style)
    - ```lang code blocks ```
    - > blockquotes
    - - list items
    - | table | rows |
    - @user:server mentions (clickable pills)
    - #room:server room links (clickable)
    - Auto-shortens Jira, GitHub, GitLab URLs
    """
    # First, shorten service URLs (before other processing)
    html = shorten_service_urls(text)

    # Extract and protect code blocks from other processing
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

    # Spoilers: ||text|| -> <span data-mx-spoiler>text</span>
    # But not table separators - check for pipe at start/end of line
    html = re.sub(r'(?<!\|)\|\|(.+?)\|\|(?!\|)', r'<span data-mx-spoiler>\1</span>', html)

    # Markdown links: [text](url) -> <a href="url">text</a>
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    # Matrix user mentions: @user:server -> clickable pill
    # Only match if not already inside a link
    html = re.sub(
        r'(?<!["\'/])(@[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )

    # Matrix room links: #room:server -> clickable link
    # Only match if not already inside a link
    html = re.sub(
        r'(?<!["\'/])(#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'<a href="https://matrix.to/#/\1">\1</a>',
        html
    )

    # Strikethrough: ~~text~~ -> <del>text</del>
    html = re.sub(r'~~(.+?)~~', r'<del>\1</del>', html)

    # Bold: **text** -> <strong>text</strong>
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

    # Italic: *text* -> <em>text</em>
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Inline code: `text` -> <code>text</code>
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)

    # Normalize multiple newlines
    html = re.sub(r'\n{2,}', '\n', html)

    # Process line-based formatting (headings, lists, blockquotes, tables)
    lines = html.split('\n')
    in_list = False
    in_quote = False
    in_table = False
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Headings: ## Heading -> <h2>
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            if in_list:
                result.append('</ul>')
                in_list = False
            if in_table:
                result.append('</table>')
                in_table = False
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            result.append(f'<h{level}>{heading_text}</h{level}>')
            continue

        # Tables: | col | col |
        if stripped.startswith('|') and stripped.endswith('|'):
            # Parse table cells
            cells = [c.strip() for c in stripped.split('|')[1:-1]]

            # Check if this is a separator line (|---|---|)
            if all(re.match(r'^[-:]+$', c) for c in cells if c):
                # Skip separator line, it's just formatting
                continue

            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            if in_list:
                result.append('</ul>')
                in_list = False

            if not in_table:
                result.append('<table>')
                in_table = True
                # First row is header
                result.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
            else:
                result.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            continue

        # Close table if we're leaving table context
        if in_table and not (stripped.startswith('|') and stripped.endswith('|')):
            result.append('</table>')
            in_table = False

        # Blockquotes: > text
        if stripped.startswith('> '):
            if not in_quote:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append('<blockquote>')
                in_quote = True
            result.append(stripped[2:])
        # Lists: - item
        elif stripped.startswith('- '):
            if in_quote:
                result.append('</blockquote>')
                in_quote = False
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append(f'<li>{stripped[2:]}</li>')
        elif stripped == '':
            # End blockquote on empty line
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

    # Close any open tags
    if in_quote:
        result.append('</blockquote>')
    if in_list:
        result.append('</ul>')
    if in_table:
        result.append('</table>')

    # Join with special marker, then convert to <br> only outside block elements
    html = '{{BR}}'.join(result)
    # Don't add <br> around block elements
    html = re.sub(r'\{\{BR\}\}(?=<ul>|<li>|</ul>|</li>|<blockquote>|</blockquote>|<pre>|<table>|<tr>|</table>|<h[1-6]>)', '', html)
    html = re.sub(r'(</ul>|</li>|</blockquote>|</pre>|</table>|</tr>|</h[1-6]>)\{\{BR\}\}', r'\1', html)
    html = re.sub(r'(<blockquote>|<table>)\{\{BR\}\}', r'\1', html)
    html = html.replace('{{BR}}', '<br>')

    # Restore code blocks
    for idx, block in enumerate(code_blocks):
        html = html.replace(f'{{{{CODEBLOCK_{idx}}}}}', block)

    return html


def add_bot_prefix(message: str, prefix: str) -> str:
    """Add bot prefix intelligently.

    If message starts with a heading, insert prefix after the heading.
    Otherwise, prepend prefix to the message.
    """
    lines = message.split('\n')
    if not lines:
        return f"{prefix} {message}"

    first_line = lines[0].strip()

    # Check if first line is a heading
    if re.match(r'^#{1,6}\s+', first_line):
        # Insert prefix after heading on same line or next line
        lines[0] = first_line
        if len(lines) > 1:
            # Insert prefix at start of content after heading
            lines.insert(1, f"\n{prefix}")
        else:
            # Add prefix after heading
            lines.append(f"\n{prefix}")
        return '\n'.join(lines)
    else:
        # Prepend prefix to message
        return f"{prefix} {message}"


def send_message(config: dict, room_id: str, message: str, format: str = "markdown",
                 emote: bool = False, thread_id: str = None, reply_id: str = None) -> dict:
    """Send a message to a Matrix room.

    Args:
        config: Matrix config with homeserver and access_token
        room_id: Room ID to send to
        message: Message content
        format: "text" or "markdown"
        emote: If True, send as m.emote (/me action)
        thread_id: Event ID of thread root (for thread replies)
        reply_id: Event ID to reply to
    """
    txn_id = str(int(time.time() * 1000))

    content = {
        "msgtype": "m.emote" if emote else "m.text",
        "body": message
    }

    if format == "markdown":
        html = markdown_to_html(message)
        if html != message:  # Only add HTML if there's actual formatting
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html

    # Thread reply (MSC3440)
    if thread_id:
        content["m.relates_to"] = {
            "rel_type": "m.thread",
            "event_id": thread_id,
            "is_falling_back": True,
        }
        # If also replying to a specific message in thread
        if reply_id and reply_id != thread_id:
            content["m.relates_to"]["m.in_reply_to"] = {"event_id": reply_id}
        else:
            content["m.relates_to"]["m.in_reply_to"] = {"event_id": thread_id}

    # Regular reply (not in thread)
    elif reply_id:
        content["m.relates_to"] = {
            "m.in_reply_to": {"event_id": reply_id}
        }

    return matrix_request(config, "PUT", f"/rooms/{room_id}/send/m.room.message/{txn_id}", content)


def clean_message(message: str) -> str:
    """Clean message from bash escaping artifacts.

    Bash history expansion in interactive shells can escape ! to \\!
    when using double quotes. This removes those artifacts.
    """
    # Remove backslash before ! (bash history expansion artifact)
    return message.replace('\\!', '!')


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send a message to a Matrix room")
    parser.add_argument("room", help="Room alias (#room:server) or room ID (!id:server)")
    parser.add_argument("message", help="Message content (markdown supported)")
    parser.add_argument("--format", choices=["text", "markdown"], default="markdown",
                        help="Message format (default: markdown)")
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
        message = add_bot_prefix(message, config["bot_prefix"])

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

    # Send message
    result = send_message(config, room_id, message, args.format,
                         emote=args.emote, thread_id=args.thread, reply_id=args.reply)

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
