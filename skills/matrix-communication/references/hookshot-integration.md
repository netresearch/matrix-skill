# Matrix Hookshot Integration

[matrix-hookshot](https://github.com/matrix-org/matrix-hookshot) is a bridge bot
that brings inbound/outbound webhooks, GitLab/GitHub connections, and RSS/Atom
feeds into a Matrix room. If the homeserver runs it, provisioning a webhook for
a room needs no dedicated script — it's driven entirely through bot commands
using the existing send/invite/power-level scripts.

## Detecting hookshot

Check the homeserver's `.well-known/matrix/client` for a managed-user pattern
matching `@hookshot:SERVER` (under `asManagedUsers`), or look for a
`uk.half-shot.matrix-hookshot.*` state event in a room that already has a
webhook bridged. If present, the bot's user ID is simply `@hookshot:SERVER`.

## Provisioning a webhook end-to-end

```bash
ROOM='!abc123:server'
BOT='@hookshot:server'

# 1. Invite the bridge bot
uv run scripts/matrix-invite.py "$ROOM" "$BOT"

# 2. Promote it — hookshot refuses to configure a bridge without moderator+
uv run scripts/matrix-power-level.py "$ROOM" --set "$BOT" 50

# 3. Ask it to create the webhook (name is free text, liveDuration optional e.g. 30d)
uv run scripts/matrix-send.py "$ROOM" "!hookshot webhook lsb-tickets" --no-prefix
```

The bot replies in the room with `"Room configured to bridge webhooks. See
admin room for secret url."` — **the actual URL is never posted in the
project room.** It's a secret, so hookshot sends it in a private 1:1 DM
between itself and whichever user issued the command.

## Retrieving the URL from the admin DM

The DM room has no name — find it by joined-member set, then read it:

```python
# find the 1:1 room with hookshot (no m.room.name set)
rooms = list_joined_rooms(config)
for r in rooms:
    if r["room_id"] == r["name"]:  # unnamed room
        members = matrix_request(config, "GET", f"/rooms/{r['room_id']}/joined_members")
        if any("hookshot" in u for u in members.get("joined", {})):
            admin_room = r["room_id"]
            break
```

```bash
uv run scripts/matrix-read.py "$ADMIN_ROOM" --limit 5 --json
```

The reply is a message like:

```text
You have bridged the webhook "lsb-tickets" in https://matrix.to/#/!abc123:server .
Please configure your webhook source to use
https://matrix.HOMESERVER/hookshot/webhooks/webhook/<uuid>
```

The admin room accumulates every webhook ever provisioned by that user across
all rooms — match on the room name/ID mentioned in the message to find the
right one if multiple webhooks were created recently.

## What a hookshot message looks like when you parse it

Reading a webhook message back — for an audit, a migration, or an event store — is not
reading `body`. Five properties, measured over 300 messages in one project room:

- **`formatted_body` carries the message; `body` carries the raw payload.** For a v2
  webhook `body` is the literal `Received webhook data:` followed by the JSON the sender
  posted. Parse `formatted_body` and fall back to `body` only when it is absent.
- **The webhook's own name is prefixed as markup**: `<strong>Production/Staging</strong>:`
  in front of the message (with the separating space). Strip it, or every title in your data starts with it.
- **An actor is rendered as a `matrix.to` link**, e.g.
  `<a href="https://matrix.to/#/@x:server">Anonymous (Incoming E-Mail)</a>: created …`.
  That link points at a person, never at the cause of the event.
- **A trailing `(?)` link is a help link**, identical across every message of the same
  sender. Taken as the message's URL it makes hundreds of messages look like duplicates
  of one another — the mistake costs whole classes of message if anything downstream
  deduplicates on a URL.
- **Glyphs arrive as HTML entities** as often as as characters: `&#9888;` for ⚠️,
  `&#9989;` for ✅. Match both, and match them anywhere in the line — a monitor puts its
  glyph in the middle (`[service] [🔴 Down] 504`).

Block tags matter when flattening to text: replace `<br>`, `</p>`, `</li>` and friends
with newlines *before* stripping tags, otherwise a package list ends up glued to the
title it follows.

## Other useful commands

Send `!hookshot help` in a bridged room to get the current list; commonly:

- `!hookshot webhook list` — show webhooks already configured in this room
- `!hookshot webhook remove <name>` — remove one
- `!hookshot gitlab project <url>` — bridge a GitLab project (requires the
  acting user to be logged in with GitLab via hookshot first)
- `!hookshot outbound-hook <name> <url>` — post room events *to* an external URL
- `!hookshot feed <url> [label] [template]` — bridge an RSS/Atom feed
