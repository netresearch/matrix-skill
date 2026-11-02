<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

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

Two details decide whether step 3 does anything:

- **`--no-prefix` is required whenever `bot_prefix` is configured.** The send
  scripts put that prefix (e.g. `🤖`) in front of the text; hookshot only reacts
  to a message that *starts* with `!hookshot`, so the prefixed command is
  ignored without a reply.
- **In an encrypted room, the bridge only sees the command if it decrypts.**
  hookshot handles encrypted rooms only when its `encryption:` config is set.
  On a bridge without it (measured on hookshot 7.5.0) the command sent with
  `matrix-send-e2ee.py` (prefix off, key shared with every device) got no reply
  and created no hook; sent as a plaintext `m.room.message` through the
  Client-Server API (what `matrix-send.py` does) it was answered within seconds.
  The command carries no secret — the URL arrives in the admin DM either way.

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

## What hookshot reads from a webhook payload

Without a transformation function, hookshot (7.5.0, `GenericHookConnection.transformHookData`)
reads exactly three keys of the posted JSON:

| Key | Becomes |
|-----|---------|
| `text` | `body` — what room previews, the notification list, pushes and non-HTML clients show |
| `html` | `formatted_body` — what Element renders in the timeline; without `html` it is rendered from `text` as Markdown |
| `username` | prepended to both: `**name**:` before `body`, `<strong>name</strong>:` before `formatted_body` (each followed by a space) |

No other key affects the message, including `version`, `msgtype`, `plain` and
`empty` (with `includeHookBody` enabled the whole payload is additionally
attached to the event as `uk.half-shot.hookshot.webhook_data`, but not
rendered). Those four belong to the **result** a transformation function
returns, and copying that schema into the webhook input is a common mistake: a
payload `{version:"v2", msgtype:"m.text", html:…}` renders fine in the
timeline, but because it has no `text`, its `body` becomes
`Received webhook data:` plus the raw JSON — which is what room previews and
the notification list show, and what a push would show once the message is
allowed to notify. Always send `text` (plain) alongside `html`.

## Message type and notifications

Without a transformation function every webhook message is sent as **`m.notice`**,
whatever the payload says. The default push rule `.m.rule.suppress_notices`
silences `m.notice` (no push, no badge count). So by default a webhook can never
wake anyone, errors included.

Two things a sender cannot change:

- **Element marks the room as unread for every visible message**, `m.notice`
  included (`eventTriggersUnreadCount` in element-web's `Unread.ts` does not
  look at `msgtype`). Only push and badge are controllable; the bold "unread"
  marker is not.
- **A muted room shows no unread state at all** (`determineUnreadState` returns
  early for `RoomNotifState.Mute`) — but muting also silences mentions, because
  Element's room mute is a user override rule that outranks the server-default
  mention rules.

To let some messages notify (e.g. errors only), the hook needs a
**transformation function** that returns `msgtype: "m.text"` for them. It is a JS
snippet in the hook's room state (`uk.half-shot.matrix-hookshot.generic.hook`,
key `transformationFunction`, state key = the hook name); hookshot runs it in
QuickJS with `data` set and reads the global `result`
(`{version:"v2", plain, html?, msgtype?, mentions?}` or `{version:"v2", empty:true}`
to drop the message). Prerequisites:

- the bridge runs with `generic.allowJsTransformationFunctions: true` — without
  it the state event is stored, but hookshot rejects it: an existing hook
  silently keeps its previous configuration, and on the next restart the hook
  fails to load at all;
- the sender of the state event holds hookshot's `manageConnections` permission
  for the `generic` service (bridge `permissions:` config; older docs called it
  `webhooks`, which still works). A room power level alone is not enough:
  hookshot verifies the sender afterwards and rolls the event back. Read the
  state back a while after writing.

A transformation applies to **every** sender on that hook. Gate any behaviour
change on a key only the intended sender sends, so other integrations posting
to the same hook keep today's result. Sketch that reproduces the built-in
handling and lets only a sender that also posts a `level` choose `m.text`:

```js
const d = (typeof data === "object" && data !== null) ? data : null;
let plain, html;
if (typeof data === "string") {
  plain = "Received webhook data: " + data;
} else if (d && typeof d.text === "string") {
  plain = d.text;
} else {
  const dump = JSON.stringify(data, null, 2);
  plain = "Received webhook data:\n\n```json\n\n" + dump + "\n\n```";
  html = "<p>Received webhook data:</p><p><pre><code class=\\\"language-json\\\">" + dump + "</code></pre></p>";
}
if (typeof data !== "string" && d) {
  if (typeof d.html === "string") { html = d.html; }
  if (typeof d.username === "string") {
    plain = "**" + d.username + "**: " + plain;
    if (html) { html = "<strong>" + d.username + "</strong>: " + html; }
  }
}
const gated = d && typeof d.level === "string" && d.level !== "" &&
  (d.msgtype === "m.text" || d.msgtype === "m.notice");
result = { version: "v2", plain: plain, msgtype: gated ? d.msgtype : "m.notice" };
if (html !== undefined) { result.html = html; }
```

Test it in hookshot's own wrapper (`const data = …; (() => { <script> })();`
then read the global `result`) before installing it.

## What a hookshot message looks like when you parse it

Reading a webhook message back — for an audit, a migration, or an event store — is not
reading `body`. Five properties, measured over 300 messages in one project room:

- **`formatted_body` carries the message; `body` may carry the raw payload.** When the
  sender posted no `text` key (see "What hookshot reads" above), `body` is the literal
  `Received webhook data:` followed by the JSON the sender posted. Parse
  `formatted_body`; falling back to `body` when it is absent only makes sense after
  checking for that prefix, or the "text" you store is the payload dump.
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
