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
  "access_token": "syt_...",
  "user_id": "@you:matrix.org",
  "bot_prefix": "🤖"
}
```

Get your access token from Element: Settings → Help & About → Access Token

**Optional fields:**
- `bot_prefix`: Emoji/text prefix for automated messages (e.g., `"🤖"`). Use `--no-prefix` to skip.

**For E2EE support** (optional):
```bash
# Install libolm
sudo apt install libolm-dev    # Debian/Ubuntu
sudo dnf install libolm-devel  # Fedora
brew install libolm            # macOS
```

## Scripts

All scripts are in the `scripts/` directory. Run with `uv run`.

| Script | Purpose |
|--------|---------|
| `matrix-send.py` | Send message (fast, non-E2EE) |
| `matrix-send-e2ee.py` | Send message (E2EE encrypted) |
| `matrix-e2ee-setup.py` | One-time E2EE device setup |
| `matrix-e2ee-verify.py` | Device verification (experimental) |
| `matrix-react.py` | React to a message with emoji |
| `matrix-edit.py` | Edit an existing message |
| `matrix-redact.py` | Delete/redact a message |
| `matrix-rooms.py` | List joined rooms |
| `matrix-read.py` | Read recent messages (unencrypted only) |
| `matrix-read-e2ee.py` | Read recent messages (E2EE decryption) |
| `matrix-resolve.py` | Resolve room alias to room ID |

## Quick Reference

```bash
# Send message to room (by alias)
uv run scripts/matrix-send.py "#myroom:matrix.org" "Hello from Claude!"

# Send message to room (by ID)
uv run scripts/matrix-send.py "!roomid:matrix.org" "Hello!"

# Send formatted message (markdown)
uv run scripts/matrix-send.py "#ops:matrix.org" "**Deployment complete** for project X"

# List joined rooms
uv run scripts/matrix-rooms.py

# Read recent messages (unencrypted only)
uv run scripts/matrix-read.py "#myroom:matrix.org" --limit 10

# Resolve room alias to ID
uv run scripts/matrix-resolve.py "#myroom:matrix.org"
```

## Message Types

### Regular Messages (m.text)
Default - use for most communication.

### Emote Messages (m.emote)
Like IRC `/me` - displays as action. Use `--emote` flag.
```bash
# Appears as: "* username is deploying to production"
uv run scripts/matrix-send.py "#ops:matrix.org" "is deploying to production" --emote
```
**When to use:** Status updates, actions, presence indicators.

### Thread Replies
Reply in a thread to keep discussions organized. Use `--thread` with root event ID.
```bash
# Start a thread or reply to existing thread
uv run scripts/matrix-send.py "#dev:matrix.org" "Update: tests passing" --thread '$rootEventId'
```
**When to use:** Ongoing updates to a topic, multi-step processes, avoiding main room clutter.

### Direct Replies
Reply to a specific message. Use `--reply` with event ID.
```bash
uv run scripts/matrix-send.py "#team:matrix.org" "Agreed, let's proceed" --reply '$eventId'
```

## Reactions

Add emoji reactions to messages to indicate status without new messages.

```bash
# React with checkmark (task done)
uv run scripts/matrix-react.py "#ops:matrix.org" '$eventId' "✅"

# Thumbs up (acknowledged)
uv run scripts/matrix-react.py "#dev:matrix.org" '$eventId' "👍"

# Eyes (looking into it)
uv run scripts/matrix-react.py "#support:matrix.org" '$eventId' "👀"
```

### Common Reaction Patterns

| Emoji | Meaning | Use Case |
|-------|---------|----------|
| ✅ | Done/Complete | Mark task as finished |
| 👍 | Acknowledged | Confirm receipt |
| 👀 | Looking into it | Started investigating |
| 🚀 | Deployed/Shipped | Indicate release |
| ⏳ | In progress | Working on it |
| ❌ | Failed/Blocked | Indicate problem |

**Workflow example:** Send "Going to reboot server" → later add ✅ reaction when complete.

## Visual Effects (Element Clients)

Include specific emoji to trigger visual effects in Element/SchildiChat:

| Emoji | Effect | Use Case |
|-------|--------|----------|
| 🎉 🎊 | Confetti | Celebrations, milestones |
| 🎆 | Fireworks | Major achievements |
| ❄️ | Snowfall | Seasonal, cool features |

```bash
# Celebrate a release
uv run scripts/matrix-send.py "#team:matrix.org" "🎉 Version 2.0 released!"
```

**Note:** Effects only show for Element/SchildiChat users. Other clients see the emoji normally.

## Message Formatting

All formatting is automatic - just use markdown syntax.

### Basic Formatting

| Syntax | Result | When to Use |
|--------|--------|-------------|
| `**bold**` | **bold** | Emphasis, headings, status |
| `*italic*` | *italic* | Secondary emphasis |
| `` `code` `` | `code` | Commands, file names, variables |
| `~~strike~~` | ~~strike~~ | Corrections, outdated info |
| `[text](url)` | linked text | Custom link labels |

### Matrix-Specific Features

| Syntax | Result | When to Use |
|--------|--------|-------------|
| `@user:server` | Clickable mention | Notify specific users |
| `#room:server` | Clickable room link | Reference other rooms |
| `> quote` | Blockquote | Quote previous messages |
| `\|\|spoiler\|\|` | Hidden text | Sensitive info, plot spoilers |
| ` ```lang ``` ` | Code block | Multi-line code with syntax highlighting |

### Smart Link Shortening

URLs are automatically shortened to readable links:

| URL | Displayed As |
|-----|--------------|
| `https://jira.*/browse/PROJ-123` | PROJ-123 |
| `https://github.com/owner/repo/issues/42` | owner/repo#42 |
| `https://github.com/owner/repo/pull/42` | owner/repo#42 |
| `https://gitlab.*/group/proj/-/issues/42` | group/proj#42 |

### Lists

```
- Item one
- Item two
- Item three
```

## When to Use Each Feature

**Deployment notifications:**
- Use **bold** for status: `**Deployed**`, `**Failed**`
- Use lists for changes
- Link to Jira issue URL (auto-shortened)

**Code sharing:**
- Use ` ```lang ``` ` for multi-line code
- Use `` `inline` `` for single commands

**Team communication:**
- Use `@user:server` to notify specific people
- Use `#room:server` to reference discussions in other rooms
- Use `> quote` when replying to earlier messages

**Sensitive information:**
- Use `||spoiler||` for credentials, secrets in examples

## E2EE Support

### Which script to use?

| Scenario | Script | Notes |
|----------|--------|-------|
| Unencrypted room | `matrix-send.py` | Fast, no deps |
| E2EE room with "allow unverified" | `matrix-send.py` | Works but not encrypted |
| E2EE room, proper encryption | `matrix-send-e2ee.py` | Requires libolm + setup |

### E2EE Setup (Recommended)

**Use a dedicated device** - this avoids key sync conflicts with Element:

```bash
# One-time setup: create dedicated E2EE device
uv run scripts/matrix-e2ee-setup.py "YOUR_MATRIX_PASSWORD"

# Now send encrypted messages
uv run scripts/matrix-send-e2ee.py '#room:server' 'Encrypted message'

# Check setup status
uv run scripts/matrix-e2ee-setup.py --status
```

**Why dedicated device?**
- Clean key state, no conflicts with Element
- Proper cross-signing setup
- Avoids "signature verification failed" errors

**⚠️ Access token fallback (not recommended):**
Using `access_token` from config reuses Element's device, which causes key sync issues and verification problems. Only use if password-based setup isn't possible.

### E2EE Script Usage

```bash
# First run after setup is slow (~5-10s) - syncs keys
uv run scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Secret message'

# Subsequent runs faster (uses cached keys)
uv run scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Another message'
```

Storage locations:
- Device credentials: `~/.local/share/matrix-skill/store/credentials.json`
- Encryption keys: `~/.local/share/matrix-skill/store/*.db`

### Device Verification (Optional)

Device verification marks a device as trusted. It's not required for E2EE to work - messages can still be encrypted/decrypted without verification.

```bash
# Wait for verification request from Element
uv run scripts/matrix-e2ee-verify.py --timeout 120

# With debug output
uv run scripts/matrix-e2ee-verify.py --debug --timeout 120
```

**Note:** Modern Matrix clients (Element) often use cross-signing and room-based verification, which may not work with this script. The device will show as "unverified" in Element but E2EE still functions.

### Reading E2EE Messages

```bash
# Read recent encrypted messages
uv run scripts/matrix-read-e2ee.py '#room:server' --limit 10

# JSON output
uv run scripts/matrix-read-e2ee.py '#room:server' --json
```

**Note:** Messages sent before your device was created show as `[Unable to decrypt]` - this is normal E2EE behavior (new devices can't read old messages without key sharing).

### Limitations

- **Old messages**: Can't decrypt messages from before device creation (no session keys)
- **First sync**: Initial run is slow due to key exchange
- **Device trust**: Auto-trusts devices (TOFU model)
- **Setup required**: First use requires user's Matrix password (one-time only)
- **Verification**: Experimental - cross-signing/room-based verification not fully supported

## Common Patterns

### Deployment notification with Jira link
```bash
uv run scripts/matrix-send.py "#ops:matrix.org" \
  "**Deployed** to production

https://jira.example.com/browse/PROJ-123

- Version: 1.2.3
- Changes: Auth improvements"
```

### Status update with mentions
```bash
uv run scripts/matrix-send.py "#dev:matrix.org" \
  "**Done**: API refactoring complete

@lead:matrix.org ready for review

See #code-review:matrix.org for PR discussion"
```

### Share code snippet
```bash
uv run scripts/matrix-send.py "#dev:matrix.org" \
  "Fix for the auth bug:

\`\`\`python
def validate_token(token):
    return token.startswith('valid_')
\`\`\`"
```

### Quote and respond
```bash
uv run scripts/matrix-send.py "#team:matrix.org" \
  "> Should we deploy today?

**Yes** - all tests passing. Deploying now."
```

### Check room before sending
```bash
# List rooms to find the right one
uv run scripts/matrix-rooms.py | grep -i ops

# Then send
uv run scripts/matrix-send.py "#ops-team:matrix.org" "Message here"
```

### Server maintenance with status updates
```bash
# 1. Announce (save event ID from output)
uv run scripts/matrix-send.py "#ops:matrix.org" "⏳ Starting server maintenance..."
# Output: Event ID: $abc123

# 2. Update status via reaction
uv run scripts/matrix-react.py "#ops:matrix.org" '$abc123' "✅"

# 3. Or add thread update
uv run scripts/matrix-send.py "#ops:matrix.org" "Maintenance complete, all services restored" --thread '$abc123'
```

### Celebrate milestone
```bash
uv run scripts/matrix-send.py "#team:matrix.org" "🎉 **Milestone reached!**

We hit 1000 users today!

Thanks to everyone who contributed."
```

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `M_FORBIDDEN` | Not in room or no permission | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Invalid/expired token | Get new token from Element |
| `M_NOT_FOUND` | Room doesn't exist | Check room alias spelling |

## Bash Quoting

**Important:** When message ends with `!`, use single quotes or `$'...'` to avoid bash history expansion adding backslashes.

```bash
# WRONG - bash escapes !" to \!
uv run scripts/matrix-send.py "#room:server" "Done!"

# CORRECT - single quotes
uv run scripts/matrix-send.py "#room:server" 'Done!'

# CORRECT - $'...' syntax
uv run scripts/matrix-send.py "#room:server" $'Done!'
```

## Related

- [Matrix Client-Server API](https://spec.matrix.org/latest/client-server-api/)
- `references/api-reference.md` - Matrix API endpoints
