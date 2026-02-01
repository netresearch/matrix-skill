"""Message formatting for Matrix scripts.

All functions use ONLY stdlib.
"""

import re


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

    for line in lines:
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
