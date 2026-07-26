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

## Other useful commands

Send `!hookshot help` in a bridged room to get the current list; commonly:

- `!hookshot webhook list` — show webhooks already configured in this room
- `!hookshot webhook remove <name>` — remove one
- `!hookshot gitlab project <url>` — bridge a GitLab project (requires the
  acting user to be logged in with GitLab via hookshot first)
- `!hookshot outbound-hook <name> <url>` — post room events *to* an external URL
- `!hookshot feed <url> [label] [template]` — bridge an RSS/Atom feed
