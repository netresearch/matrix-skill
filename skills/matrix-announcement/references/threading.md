# Threads, mentions, edits, redactions

## Threading

A long announcement should not become a long message. Post the headline + summary as the parent; put extended notes, screenshots, and Q&A follow-ups in a thread.

A spec-compliant threaded reply has three relation fields — `rel_type`, the thread root `event_id`, an `is_falling_back` flag, and an `m.in_reply_to` pointing at the parent (root or last reply) so non-thread-aware clients still render the message as a normal reply:

```json
"m.relates_to": {
  "rel_type": "m.thread",
  "event_id": "$thread_root_event_id",
  "is_falling_back": true,
  "m.in_reply_to": {
    "event_id": "$parent_event_id"
  }
}
```

`event_id` is always the thread root. `m.in_reply_to.event_id` is the previous message in the thread (or the root for the first reply). `is_falling_back: true` tells thread-aware clients to suppress the reply UI — the `m.in_reply_to` is purely a fallback for older clients.

When in doubt, thread it. Rooms scroll fast.

## Mentions

Tag people only when they actually need to see it. Use proper Matrix mentions, not plaintext `@name`:

```html
cc <a href="https://matrix.to/#/@sebastian:netresearch.de">@sebastian</a>
```

Include the mentions block (MSC3952, now spec) so notifications fire correctly:

```json
"m.mentions": {
  "user_ids": ["@sebastian:netresearch.de"]
}
```

For room-wide pings (`@room`), set `"room": true` in `m.mentions`. **Reserve them for outages** — every misuse trains people to mute the room.

## Edits

If you need to fix a typo within ~5 minutes, edit:

```json
{
  "msgtype": "m.text",
  "body": "* corrected text",
  "format": "org.matrix.custom.html",
  "formatted_body": "* <p>corrected text</p>",
  "m.new_content": {
    "msgtype": "m.text",
    "body": "corrected text",
    "format": "org.matrix.custom.html",
    "formatted_body": "<p>corrected text</p>"
  },
  "m.relates_to": {
    "rel_type": "m.replace",
    "event_id": "$original_event_id"
  }
}
```

The outer `body` / `formatted_body` is the fallback text shown by clients that don't render edits — prefix it with `*` so the asterisk indicates "this is an edit". `m.new_content` is the replacement content; if you set `format: org.matrix.custom.html`, `formatted_body` must be valid HTML.

If the message is already an hour old, **post a follow-up reply instead** — edits to old messages are easy to miss and notification-silent.

## Redactions

Redact only when the content is **wrong-and-harmful**:

- Leaked secret (token, password, API key)
- Mistargeted ping that woke up the wrong on-call rotation
- Personal data published to a public room

**Never redact "to clean up"** — the audit trail is more valuable than tidiness, and redactions are themselves visible events that draw attention.

```json
{
  "type": "m.room.redaction",
  "redacts": "$event_id_to_redact",
  "content": {
    "reason": "leaked secret"
  }
}
```

Always include a `reason`. Redactions without context look like coverups.
