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

### Notice Messages (m.notice)
Bot-flagged. Clients render `m.notice` visually distinct (usually muted) and **other bots are forbidden from auto-replying** to it — this prevents bot-on-bot loops. Use `--notice` flag (mutually exclusive with `--emote`).
```bash
# Unattended automation: release announcement from CI
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py "#releases:example.com" \
    "📦 Release: jira-skill v3.12.0 — progressive-disclosure refactor" --notice
```
**When to use:** Release announcements, CI summaries, scheduled digests, alert pings — anything posted unattended without a human reviewing first. For agent-on-behalf-of-human posts where a reply would be welcome, leave it as the default `m.text`.

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

Unified team vocabulary (2026-08-13). Downstream copies of this table exist —
when changing semantics here, keep them in sync:

| Emoji | Meaning | Use Case |
|-------|---------|----------|
| ▶️ | Actively working NOW | Set on the claim message; REDACT it when work stops — a lingering ▶️ reads as "still busy" |
| ✅ | Done/Complete | Mark task as finished |
| ⏳ | Waiting/queued | Nobody actively on it (NOT "in progress" — that is ▶️) |
| 🚀 | Deployed/Shipped | Indicate release |
| ❌ | Attempt failed | Distinct from 👎 (declining) and ↩️ (questions) |
| 👀 | Looking at it | No commitment to work on it |
| ↩️ | Back to reporter | Went back with questions |
| 💡 | Helpful | This message taught me something |
| 🤖 | Agent read-receipt | The agent read it and tries to heed it |
| 👍 | Agreement, I'm in | NOT a receipt acknowledgement (that is 🤖) |
| 👎 | Count me out | Rather not |

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

## Reading Reactions

Reactions are `m.reaction` events that reference a target event via `relates_to`. When reading room history with `--json`, reactions appear as separate events.

### How Reactions Work

- Each reaction is a standalone `m.reaction` event
- The `content.m.relates_to` field links it to the original message
- `rel_type` is always `m.annotation`
- `key` contains the emoji or text of the reaction

### JSON Output Structure

```json
{
  "type": "m.reaction",
  "sender": "@user:server",
  "content": {
    "m.relates_to": {
      "rel_type": "m.annotation",
      "event_id": "$original_message_id",
      "key": "👍"
    }
  }
}
```

### Analyzing Reactions Programmatically

Use `--json` output and filter for `m.reaction` events:

```bash
# Read room history as JSON
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py room-name --limit 200 --json

# Use jq to extract reactions for a specific event
... | jq '[.[] | select(.type == "m.reaction") | {sender: .sender, emoji: .content."m.relates_to".key, target: .content."m.relates_to".event_id}]'
```

### Use Case: Polls and Attendance via Reactions

Reactions can serve as lightweight polls. Post a message with options and ask users to react:

1. Send a message with options (e.g., "React with your lunch preference: 🍕 Pizza, 🍔 Burger, 🥗 Salad")
2. Read reactions with `--json` and group by emoji `key`
3. Count unique senders per emoji to tally votes

## Mentions

A plain `@name` in the body notifies nobody. It only ever matched the legacy
`contains_user_name` push rule, and only on the exact localpart — `@bjoern`
never reached `bjoern.marten`. What notifies a modern client is `m.mentions`
(MSC3952).

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM \
  "bjoern.marten, schaust du drauf?" --mention '@bjoern.marten:server'

# everyone in the room
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "Wartung 22:00" --mention-room
```

`--mention` is repeatable and does two things:

- sets `content["m.mentions"]["user_ids"]`, which is what fires the notification
- turns the first occurrence of that localpart in the text into a pill, in the
  **HTML body only**

The plain body keeps the bare name on purpose: it is what a client without HTML
shows, and what the legacy push rule reads.

A name that does not appear in the text is not inserted. The mention still
notifies; silently rewriting a message to add a name the author did not type is
worse than a missing pill. A name already written as a `matrix.to` link is left
alone rather than wrapped twice.

By hand, without the flag:

```markdown
[bjoern.marten](https://matrix.to/#/@bjoern.marten:server)
```

That renders a pill and keeps the localpart in the plain body — but `m.mentions`
stays absent, so it looks like a mention and does not notify.
