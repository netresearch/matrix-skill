# Threads, mentions, edits, redactions

## Threading

A long announcement should not become a long message. Post the headline + summary as the parent; put extended notes, screenshots, and Q&A follow-ups in a thread:

```json
"m.relates_to": {
  "rel_type": "m.thread",
  "event_id": "$parent_event_id"
}
```

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
  "m.new_content": {
    "msgtype": "m.text",
    "body": "corrected text",
    "format": "org.matrix.custom.html",
    "formatted_body": "corrected text"
  },
  "m.relates_to": {
    "rel_type": "m.replace",
    "event_id": "$original_event_id"
  }
}
```

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
