<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

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
| 🩹 | Fix handed over | MR/PR provided, work stopped, the team has to review |
| ⏳ | Waiting/queued | Nobody actively on it (NOT "in progress" — that is ▶️) |
| 🚀 | Deployed/Shipped | Indicate release |
| ❌ | Attempt failed | Distinct from 👎 (declining) and ↩️ (questions) |
| 👀 | Looking at it | No commitment to work on it |
| ↩️ | Back to reporter | Went back with questions |
| 💡 | Helpful | This message taught me something |
| 🤖 | Agent read-receipt | The agent read it and tries to heed it. On a ticket notification it means something else, see below |
| 👍 | Agreement, I'm in | NOT a receipt acknowledgement (that is 🤖) |
| 👎 | Count me out | Rather not |

**Workflow example:** Send "Going to reboot server" then later add checkmark reaction when complete.

### Reactions on ticket notifications

A ticket tracker bridged into a room (for example Jira through a hookshot
webhook) posts one message per ticket event. The team reads ticket state from
these messages, so an agent that works on a ticket reacts to its notification:

| Emoji | Meaning |
|-------|---------|
| ▶️ | An agent is working on the ticket right now |
| 🩹 | MR/PR provided, the agent stopped, the team has to review |
| ✅ | Done: the ticket is in QA, Resolved or Closed |
| 🤖 | An agent works or worked on this ticket. Here it is NOT a read-receipt |

The same reactions go on every other automated notification whose symptom an
agent works on: a failed build or deploy, a dependency-bot warning, an
application error forwarded by a webhook. ✅ there means the symptom is
resolved or explained with no change needed; 🩹 means a fix waits for review
or merge; ▶️ means the agent is still on it, for example while a rollout runs.

Rules:

1. Set exactly ONE of ▶️, 🩹 or ✅ per notification, and always 🤖 next to it.
   Rule 4 names the one state without a status.
2. Change the status with ONE call: `--replace` sets the new status and
   removes the account's own reactions with the old ones. The script finds
   those reactions on the server, so no reaction id is needed. It sends the
   new status first, and it does not send a status the account already set.
3. Set ▶️ + 🤖 when the agent claims the ticket, swap to 🩹 at the MR/PR
   handover, swap to ✅ when the ticket goes to QA or is resolved.
4. Before reporting the work done, compare each status you set with the
   ticket's live status. A person can move the ticket after you: a ticket
   someone reopened loses ✅ (`--remove`) and carries no status until one
   applies again, such as ▶️ when work on it resumes. 🤖 stays. This is the
   one state without a status reaction. `--list` shows what the account has
   set on a notification.
5. React only on a notification the team still sees. When a ticket's
   notification has scrolled far back in the room, nobody reads its
   reactions anymore, so skip it rather than search for it: a reaction
   there is work without a reader. The same holds for a ticket whose
   notification is not in the room at all.

```bash
R=skills/matrix-communication/scripts/matrix-react.py
uv run $R ROOM '$eventId' "▶️" --replace "🩹" "✅"   # claim
uv run $R ROOM '$eventId' "🤖"
uv run $R ROOM '$eventId' "🩹" --replace "▶️" "✅"   # MR/PR handed over
uv run $R ROOM '$eventId' "✅" --replace "▶️" "🩹"   # QA / resolved
uv run $R ROOM '$eventId' "▶️" --remove               # take one back
uv run $R ROOM '$eventId' --list                      # what this account has set
```

Pass the room ID (`!…:server`) when you have it. A room name is resolved by
reading every joined room: on an account in many rooms that took 40 s per
call, against 0.7 s with the room ID (measured 2026-11-04).

Finding the notification: each room can have its own webhook sender, so a
filter on one sender name misses the other rooms. Filter on the user-ID prefix
the bridge's webhook senders share AND on the ticket URL (`/browse/<KEY>`) in
`body`. Read only the recent part of the room, about what a member still sees
on opening it; a notification that is not in it falls under rule 5 and gets
no reaction, so a deeper search is not needed:

```bash
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM --limit 50 --json
```

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

Reactions are `m.reaction` events that reference a target event via `relates_to`. In an encrypted room a reaction can also arrive as `m.room.encrypted`; its `m.relates_to` stays in clear text, so filter on the relation (`rel_type: m.annotation` and its `key`), not on the event type. `matrix-read-e2ee.py` does not return reactions: it emits room messages only (`m.room.message` and undecryptable `m.room.encrypted`). Read the reactions on one event through the relations API instead, which is what `matrix-react.py --list` does for the account's own reactions.

### How Reactions Work

- Each reaction is a standalone `m.reaction` event (or `m.room.encrypted` with a clear-text `m.relates_to`)
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

The account's own reactions on one event, as emoji and reaction event ID:

```bash
uv run skills/matrix-communication/scripts/matrix-react.py ROOM '$eventId' --list [--json]
```

Every sender's reactions on one event come from
`GET /_matrix/client/v1/rooms/{roomId}/relations/{eventId}/m.annotation`;
follow `next_batch` until it is absent. Each `chunk` entry has the shape above;
an encrypted one has `"type": "m.room.encrypted"` with the same `m.relates_to`.

### Use Case: Polls and Attendance via Reactions

Reactions can serve as lightweight polls. Post a message with options and ask users to react:

1. Send a message with options (e.g., "React with your lunch preference: 🍕 Pizza, 🍔 Burger, 🥗 Salad")
2. Read the reactions on that message through the relations API and group by emoji `key`
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
