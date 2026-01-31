---
name: matrix-communication
description: Matrix chat communication. AUTOMATICALLY TRIGGER when user mentions Matrix rooms (#room:server), asks to send messages to chat, or wants to interact with Matrix. Use for sending messages to Matrix rooms on behalf of users via access token authentication.
---

# Matrix Communication

Send messages to Matrix chat rooms on behalf of users.

## Auto-Trigger

**AUTOMATICALLY USE THIS SKILL** when you encounter:
- **Room references**: `#room:server`, `!roomid:server`
- **Chat requests**: "send to matrix", "post in chat", "notify the team"
- **Matrix URLs**: `https://matrix.*/`, `https://element.*/`

## Prerequisites

**Config file:** `~/.config/matrix/config.json`

```json
{
  "homeserver": "https://matrix.org",
  "access_token": "syt_..."
}
```

Get your access token from Element: Settings → Help & About → Access Token

## Scripts

All scripts are in the `scripts/` directory. Run with `uv run`.

| Script | Purpose |
|--------|---------|
| `matrix-send.py` | Send message to a room |
| `matrix-rooms.py` | List joined rooms |
| `matrix-read.py` | Read recent messages (unencrypted only) |
| `matrix-resolve.py` | Resolve room alias to room ID |

## Quick Reference

```bash
# Send message to room (by alias)
uv run scripts/matrix-send.py "#test:netresearch.de" "Hello from Claude!"

# Send message to room (by ID)
uv run scripts/matrix-send.py "!roomid:netresearch.de" "Hello!"

# Send formatted message (markdown)
uv run scripts/matrix-send.py "#ops:netresearch.de" "**Deployment complete** for project X"

# List joined rooms
uv run scripts/matrix-rooms.py

# Read recent messages (unencrypted only)
uv run scripts/matrix-read.py "#test:netresearch.de" --limit 10

# Resolve room alias to ID
uv run scripts/matrix-resolve.py "#test:netresearch.de"
```

## Message Formatting

Matrix supports HTML formatting. The `matrix-send.py` script automatically converts markdown to Matrix HTML format.

| Markdown | Matrix HTML |
|----------|-------------|
| `**bold**` | `<strong>bold</strong>` |
| `*italic*` | `<em>italic</em>` |
| `` `code` `` | `<code>code</code>` |
| `- item` | `<ul><li>item</li></ul>` |

## E2EE Limitations

**V1 (Current):**
- Sending: Works to E2EE rooms (if "allow unverified devices" is enabled)
- Reading: Only unencrypted messages (webhooks, API-sent messages)

**V2 (Planned):** Full read support for unencrypted rooms
**V3 (Future):** Full E2EE support with Megolm key management

## Common Patterns

### Notify team about deployment
```bash
uv run scripts/matrix-send.py "#ops:netresearch.de" \
  "**Deployment Complete**\n\n- Project: MyApp\n- Version: 1.2.3\n- Environment: Production"
```

### Send status update
```bash
uv run scripts/matrix-send.py "#dev:netresearch.de" \
  "Task NRS-1234 completed. Changes deployed to staging."
```

### Check room before sending
```bash
# List rooms to find the right one
uv run scripts/matrix-rooms.py | grep -i ops

# Then send
uv run scripts/matrix-send.py "#ops-team:netresearch.de" "Message here"
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `M_FORBIDDEN` | Not in room or no permission | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Invalid/expired token | Get new token from Element |
| `M_NOT_FOUND` | Room doesn't exist | Check room alias spelling |

## Related

- [Matrix Client-Server API](https://spec.matrix.org/latest/client-server-api/)
- `references/api-reference.md` - Matrix API endpoints
