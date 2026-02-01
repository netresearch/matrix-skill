#!/usr/bin/env python3
"""Send a message to a Matrix room.

Usage:
    matrix-send.py ROOM MESSAGE [OPTIONS]
    matrix-send.py --help

Arguments:
    ROOM        Room identifier. Supports multiple formats:
                - Room ID: !abc123xyz (direct, fastest)
                - Room alias: #room:server (resolved via directory)
                - Room name: "agent-work" (looked up from joined rooms)
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

Examples:
    # Send by room name (easiest)
    matrix-send.py agent-work "Hello team!"

    # Send by room ID (from matrix-rooms.py output)
    matrix-send.py '!sZBoTOreI1z0BgHY-s2ZC9MV63B1orGFigPXvYMQ22E' "Hello!"

    # Send by alias
    matrix-send.py '#general:matrix.org' "Hello everyone!"
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


def get_room_info(config: dict, room_id: str) -> dict:
    """Get the display name and canonical alias of a room."""
    info = {"name": None, "alias": None}

    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.name")
    if "name" in result:
        info["name"] = result["name"]

    result = matrix_request(config, "GET", f"/rooms/{room_id}/state/m.room.canonical_alias")
    if "alias" in result:
        info["alias"] = result["alias"]

    return info


def list_joined_rooms(config: dict) -> list:
    """List all joined rooms with names and aliases."""
    result = matrix_request(config, "GET", "/joined_rooms")
    if "error" in result:
        return []

    rooms = []
    for room_id in result.get("joined_rooms", []):
        info = get_room_info(config, room_id)
        display_name = info["name"] or info["alias"] or room_id
        rooms.append({
            "room_id": room_id,
            "name": display_name,
            "alias": info["alias"]
        })

    return rooms


def find_room_by_name(config: dict, search_term: str) -> tuple[str | None, list]:
    """Find a room by name or alias (case-insensitive).

    Returns (room_id, matches) where:
    - room_id is the matched room ID (or None if no/ambiguous match)
    - matches is list of matching rooms (for error reporting)
    """
    rooms = list_joined_rooms(config)
    search_lower = search_term.lower()

    # Try exact match first
    for room in rooms:
        if room["name"].lower() == search_lower:
            return room["room_id"], [room]
        if room.get("alias") and room["alias"].lower() == search_lower:
            return room["room_id"], [room]
        # Match alias without server part (e.g., "agent-work" matches "#agent-work:server")
        if room.get("alias"):
            alias_name = room["alias"].split(":")[0].lstrip("#")
            if alias_name.lower() == search_lower:
                return room["room_id"], [room]

    # Try partial match
    matches = []
    for room in rooms:
        if search_lower in room["name"].lower():
            matches.append(room)
        elif room.get("alias") and search_lower in room["alias"].lower():
            if room not in matches:
                matches.append(room)

    if len(matches) == 1:
        return matches[0]["room_id"], matches

    return None, matches


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
    parser.add_argument("room", help="Room ID (!id), alias (#room:server), or name")
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

    # Resolve room to room ID
    room_id = args.room
    room_input = args.room

    if room_input.startswith("!"):
        # Direct room ID - use as-is
        room_id = room_input
        if args.debug:
            print(f"Using room ID directly: {room_id}", file=sys.stderr)

    elif room_input.startswith("#"):
        # Room alias - try to resolve
        try:
            room_id = resolve_room_alias(config, room_input)
            if args.debug:
                print(f"Resolved alias {room_input} -> {room_id}", file=sys.stderr)
        except ValueError as e:
            # Alias resolution failed - try name lookup as fallback
            alias_name = room_input.split(":")[0].lstrip("#")
            if args.debug:
                print(f"Alias resolution failed, trying name lookup for '{alias_name}'", file=sys.stderr)

            found_id, matches = find_room_by_name(config, alias_name)
            if found_id:
                room_id = found_id
                if args.debug:
                    print(f"Found room by name: {room_id}", file=sys.stderr)
            else:
                error_msg = f"Could not resolve room '{room_input}'"
                if matches:
                    error_msg += f". Multiple matches found:\n"
                    for m in matches:
                        alias_str = f" ({m['alias']})" if m.get("alias") else ""
                        error_msg += f"  - {m['name']}{alias_str}: {m['room_id']}\n"
                else:
                    error_msg += ". Room not found in joined rooms."
                if args.json:
                    print(json.dumps({"error": error_msg}))
                else:
                    print(f"Error: {error_msg}", file=sys.stderr)
                sys.exit(1)

    else:
        # Plain name - look up by name
        if args.debug:
            print(f"Looking up room by name: '{room_input}'", file=sys.stderr)

        found_id, matches = find_room_by_name(config, room_input)
        if found_id:
            room_id = found_id
            if args.debug:
                print(f"Found room: {room_id}", file=sys.stderr)
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
