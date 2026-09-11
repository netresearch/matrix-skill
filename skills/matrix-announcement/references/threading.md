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

**A maintenance window gets one thread per ticket.** A window room carrying three
tickets in one flat timeline interleaves them, and a reader who cares about one
of them has to reconstruct which line belongs to which — at the moment they are
least able to. One thread per ticket, rooted on the message that claims it, and
the room's flat level carries only what is true of the whole window: it opened,
it closed, an incident started, an incident ended. The closing note for each
ticket goes in that ticket's thread *and* nowhere else, so the thread reads as a
complete story on its own.

## Timestamps

**An absolute time carries the zone it was measured in.** Not the zone you
assume, and not UTC unless that is what you actually read: a window spans a DST
boundary about twice a year, its operators sit in more than one offset, and the
logs quoted into the room are frequently in a third. "21:20" in a room whose
readers are working from a UTC log is a number that has to be guessed at, and it
is guessed at wrongly in exactly the situation the message exists for.

Write `21:20 CEST`, or `19:20 UTC`, and where a message quotes a log line, say
which zone the line itself used — for example *21:06:40 CEST, from the host's
own `date`*.
Relative times (*in ~10 minutes*, *for the last half hour*) need no zone and are
usually the kinder form for a heads-up; they just cannot be reconstructed
afterwards, so anything meant for the record gets the absolute form as well.

## Mentions

Tag people only when they actually need to see it. Use proper Matrix mentions, not plaintext `@name`:

```html
cc <a href="https://matrix.to/#/@sebastian:example.com">@sebastian</a>
```

Include the mentions block (MSC3952, now spec) so notifications fire correctly:

```json
"m.mentions": {
  "user_ids": ["@sebastian:example.com"]
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
