# Matrix Messaging Guide

Message formatting, reactions, visual effects, and common communication patterns.

## Message Types

### Regular Messages (m.text)
Default -- use for most communication.

### Emote Messages (m.emote)
Like IRC `/me` -- displays as action. Use `--emote` flag.
```bash
# Appears as: "* username is deploying to production"
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py "#ops:matrix.org" "is deploying to production" --emote
```
**When to use:** Status updates, actions, presence indicators.

### Thread Replies
Reply in a thread to keep discussions organized. Use `--thread` with root event ID.
```bash
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py "#dev:matrix.org" "Update: tests passing" --thread '$rootEventId'
```
**When to use:** Ongoing updates, multi-step processes, avoiding main room clutter.

### Direct Replies
Reply to a specific message. Use `--reply` with event ID.
```bash
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py "#team:matrix.org" "Agreed, let's proceed" --reply '$eventId'
```

## Reactions

Add emoji reactions to indicate status without new messages.

```bash
uv run skills/matrix-communication/scripts/matrix-react.py "#ops:matrix.org" '$eventId' "checkmark"
uv run skills/matrix-communication/scripts/matrix-react.py "#dev:matrix.org" '$eventId' "thumbs-up"
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

**Workflow example:** Send "Going to reboot server" then later add checkmark reaction when complete.

## Visual Effects (Element Clients)

Include specific emoji to trigger visual effects in Element/SchildiChat:

| Emoji | Effect | Use Case |
|-------|--------|----------|
| 🎉 / 🎊 | Confetti | Celebrations, milestones |
| 🎆 | Fireworks | Major achievements |
| ❄️ | Snowfall | Seasonal, cool features |

**Note:** Effects only show for Element/SchildiChat users. Other clients see the emoji normally.

## Message Formatting

All formatting is automatic -- just use markdown syntax.

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
| `\|\|spoiler\|\|` | Hidden text | Sensitive info |
| ` ```lang ``` ` | Code block | Multi-line code with highlighting |

### Smart Link Shortening

URLs are automatically shortened:

| URL | Displayed As |
|-----|--------------|
| `https://jira.*/browse/PROJ-123` | PROJ-123 |
| `https://github.com/owner/repo/issues/42` | owner/repo#42 |
| `https://github.com/owner/repo/pull/42` | owner/repo#42 |
| `https://gitlab.*/group/proj/-/issues/42` | group/proj#42 |

## Common Patterns

### Deployment notification with Jira link
```bash
uv run .../matrix-send-e2ee.py "#ops:matrix.org" \
  "**Deployed** to production

https://jira.example.com/browse/PROJ-123

- Version: 1.2.3
- Changes: Auth improvements"
```

### Status update with mentions
```bash
uv run .../matrix-send-e2ee.py "#dev:matrix.org" \
  "**Done**: API refactoring complete

@lead:matrix.org ready for review

See #code-review:matrix.org for PR discussion"
```

### Share code snippet
```bash
uv run .../matrix-send-e2ee.py "#dev:matrix.org" \
  "Fix for the auth bug:

\`\`\`python
def validate_token(token):
    return token.startswith('valid_')
\`\`\`"
```

### Server maintenance with status updates
```bash
# 1. Announce (save event ID from output)
uv run .../matrix-send-e2ee.py "#ops:matrix.org" "Starting server maintenance..."
# Output: Event ID: $abc123

# 2. Update status via reaction
uv run .../matrix-react.py "#ops:matrix.org" '$abc123' "checkmark"

# 3. Or add thread update
uv run .../matrix-send-e2ee.py "#ops:matrix.org" "Maintenance complete" --thread '$abc123'
```

### Check room before sending
```bash
uv run .../matrix-rooms.py | grep -i ops
uv run .../matrix-send-e2ee.py "#ops-team:matrix.org" "Message here"
```

## When to Use Each Feature

**Deployment notifications:**
- Use **bold** for status
- Use lists for changes
- Link to Jira issue URL (auto-shortened)

**Code sharing:**
- Use fenced code blocks for multi-line code
- Use inline code for single commands

**Team communication:**
- Use `@user:server` to notify specific people
- Use `#room:server` to reference other rooms
- Use `> quote` when replying to earlier messages

**Sensitive information:**
- Use `||spoiler||` for credentials or secrets in examples
