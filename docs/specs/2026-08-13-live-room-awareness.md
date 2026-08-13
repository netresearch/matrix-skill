---
type: design
title: Live room awareness for coding agents
description: A daemon that owns the E2EE store, streams decrypted room events to a JSONL log, and accepts send/react commands over a socket, so an agent can follow a room while it works.
resource: https://github.com/netresearch/matrix-skill/tree/main/docs/specs/2026-08-13-live-room-awareness.md
tags: [matrix, e2ee, daemon, agent-integration, design]
timestamp: 2026-08-13T00:00:00+02:00
---

# Live room awareness for coding agents

## Problem

An agent working in a coding session cannot follow a Matrix room. It can send a
message and it can read on demand, but reading means starting a process, syncing,
and blocking until it finishes. Anything said in the room while the agent works
reaches it only when someone thinks to ask.

The goal is the opposite: the agent stays current with a room while it works, can
post its own status and reactions without leaving what it is doing, and can
answer promptly when a message concerns the work in progress.

## The constraint that shapes everything

Only one process may hold the E2EE store. This is not a preference. Two nio
processes on one store produce corruption and errors that name the wrong thing —
during the work that led to this spec, a store was left as
`*.db.corrupt-<date>`, and a concurrent access surfaced as
`OlmAccountError: BAD_ACCOUNT_KEY`, which reads as a credential problem.

A second constraint follows from Matrix itself: **sync is account-wide and
to-device events are consumed once per device.** Whichever process syncs receives
the room keys and verification requests for every room, and the next sync from
that device will not see them again. Several processes syncing in turn means keys
land wherever the race puts them.

Both constraints point the same way: one long-lived process syncs and owns the
store, everything else goes through it.

## Architecture

Three roles, one of them long-lived.

**The daemon** holds the store, syncs continuously, decrypts, appends each event
to a per-room JSONL log, and serves a Unix socket. It has no contact with any
agent session and outlives all of them.

Sync and socket run as two tasks on one asyncio event loop, sharing one client.
This is not an implementation detail to settle later: a sync is a long poll of up
to 30 seconds, so a daemon that served the socket only between syncs would answer
a send after an arbitrary delay of up to that long — and a send that takes half a
minute is not the "answer promptly" this exists for. One loop also keeps every
store access single-threaded without a mutex, because nio's client is safe within
one loop and not across threads.

**The attach** is a thin reader over the JSONL. It never touches the store, so it
can run any number of times in parallel, and it dies with the session that
started it. Its stdout is one line per event, which is the input shape the
agent's monitoring mechanism already consumes.

It exists as a script rather than a raw `tail -F` for three jobs and no others:
resolve a room name or alias to its slug, emit the one-line summary from the
cursor before going live, and advance the cursor. After that it is a tail. If it
grows a fourth job, that job belongs in the daemon.

It reads the file with stdlib `json` rather than piping through `jq`. The
repository's helper library is stdlib-only on purpose, and a reader that is the
first thing to require an external binary would make the feature conditional on
that binary being installed.

**The commands** — send, react, redact — are the existing scripts with one
addition: they try to connect to the socket first. A connection that succeeds
means a daemon is running and the operation goes over it. A refused connection or
a missing socket means no daemon, and the command takes the store lock itself and
works exactly as it does today. The skill therefore keeps working unchanged when
no daemon runs, and no one has to remember two ways to send a message.

**The routing signal is the socket, not the lock.** Deciding on the lock would be
wrong in a way that is easy to miss: a direct `matrix-send-e2ee.py` holds the same
lock for its couple of seconds, so a second command starting in that window would
see a held lock, conclude "daemon", and try to talk to a socket that nobody is
serving. The lock answers "may I open the store", which is a different question
from "is there someone to delegate to", and only the socket answers the second
one.

Ownership itself is still enforced rather than agreed: the daemon holds an
advisory `flock` on the store directory for its whole life, and every direct path
takes the same lock before opening the store. The failure mode this replaces was a
convention that nothing checked.

### Data flow

A message someone types reaches the agent as: homeserver → daemon sync →
decryption → one line appended to the room's JSONL → `tail -F` in the attach →
event in the agent's session.

A reply travels the other way over the socket, and then returns through the same
JSONL path. The agent sees its own message the way everyone else sees it, not the
way it sent it.

## Interfaces

### Event log — JSONL, one record per line

`~/.local/share/matrix-skill/rooms/<slug>.jsonl`

The slug is the room id without `!` and with `_` for `:`. Not cosmetic: a `!` in a
filename is a hazard in every shell invocation.

Each record carries `seq`, a timestamp, `event_id`, sender with display name, type
(`m.text`, `m.notice`, `m.emote`, reaction, redaction, membership), body,
`reply_to`, `thread_root`, a `self` flag for the agent's own messages, a
`mentions_me` flag, and a `text` field holding the finished display line —
`[23:15] tobias.hein: Ihr seid cool`. The `text` field means the reader prints a
field instead of formatting an event, and it keeps the raw file readable to a
human.

An event that applies to another one also carries what it applies to: a reaction
its `relates_to`, a redaction its `redacts` and `reason`. Without them a reader
sees that something was reacted to or removed and cannot tell which, which is
close enough to no information that it invites a wrong guess. The daemon keeps
the last few hundred bodies per room so the display line can name the target;
past that window the line says only that it happened, rather than printing an
event id that identifies the target to nobody reading.

`seq` is a per-room counter that only increases. It is what the cursor compares
against, so counting what was missed is subtraction rather than a file scan —
which also survives log rotation, where an `event_id`-only cursor would point
into a file that no longer exists.

`mentions_me` is computed by the daemon, once, per event: the account's localpart
or current display name appearing in the body, or the event being a reply to one
of the agent's own events. Computing it in the reader would mean every attach
re-deriving the same answer from a display name it would have to look up.

JSONL rather than OKF is a deliberate exception to this repository's format
preference, and it follows OKF's own scope: the specification defines one concept
per file with no provision for multiple records or streams, and its only
log-shaped construct, `log.md`, is ordered most-recent-first — every append would
rewrite the whole file, several times a minute for a busy room.

### Room bundle — OKF

`~/.local/share/matrix-skill/rooms/index.md` plus one `<slug>.md` per watched
room, `type: matrix-room`, carrying alias, display name, `resource`, and
timestamp. This is knowledge about rooms rather than a stream, so it takes the
repository's normal format, and it replaces what would otherwise be an ad-hoc
JSON mapping.

### Cursor

`<slug>.cursor` holds the last `seq` an attach saw. On attach the reader counts
what arrived since, prints one summary line — `since last: 47 messages, 3
mentioning you` — advances the cursor, and goes live. `--cursor NAME` separates
sessions that follow the same room.

Counting reads backwards from the end of the log until it passes the stored
`seq`, so the cost is the size of the gap and not the size of the history. A
cursor whose `seq` is older than the oldest record still in the log — because
rotation dropped it — reports the count as a lower bound rather than pretending
to a number it cannot know.

### Socket

`$XDG_RUNTIME_DIR/matrix-skill/daemon.sock`, newline-delimited JSON,
request/response. Operations: `send`, `react`, `redact`, `status`. Responses are
`{"ok": true, "event_id": "$…"}` or `{"ok": false, "error": "…"}`.

No authentication: mode `0600`, same user, no network binding.

### Commands

```
matrix-watchd.py --start | --stop | --status | --foreground
matrix-watch.py ROOM [--cursor NAME]
```

Existing commands gain no new flags.

### Configuration

One key in `~/.config/matrix/config.json`:

```json
{"watch_rooms": ["#it:example.org"]}
```

## Lifecycle

`--start` detaches, writes pid and socket under `$XDG_RUNTIME_DIR/matrix-skill/`,
and takes the store lock. If the lock is already held it refuses and names the
holding pid rather than starting a second syncer.

`--stop` is SIGTERM: close the store, remove the socket.

After a crash a socket file remains with nothing listening. Clients detect
`ECONNREFUSED`, unlink it, and continue in direct mode. There is no state that
requires manual repair.

## Failure handling

**Undecryptable events are written, not dropped**, as a record whose `text` reads
`[unable to decrypt]` and which carries the `session_id`. The agent learns that
something arrived. The daemon requests the keys, and a successful retry appends a
correction record with the same `event_id`.

That is the one case where an `event_id` appears twice in a log. A later record
supersedes an earlier one with the same id; consumers must not assume a record is
final. Appending rather than rewriting is what keeps the file append-only, and a
reader that already displayed the placeholder shows the correction as a new line
rather than silently changing history.

**A revoked token stops the daemon loudly.** It writes a final record naming the
cause into every log before exiting, so the reason appears as a line in the
agent's session. A watcher that dies quietly is indistinguishable from a quiet
room — that failure happened during the work behind this spec and cost real time.

Sync errors retry with growing backoff. Logs rotate at a size limit; `tail -F`
follows rotation on its own.

## Testing

Testable without a homeserver, and therefore tested: record construction from an
event including the `text` rendering, the slug function, cursor counting with and
without mentions, and the client's routing decision — lock held goes to the
socket, lock free goes direct. The socket paths and the fallback are covered
against a fake listener in a temporary directory.

**Not covered:** the sync loop itself, which needs a live homeserver. Stated here
rather than papered over with a mock test that would only prove the mock matches
the mock.

## Decisions and risks

**The agent may reply on its own.** Requested explicitly. It means the agent
posts into a room where colleagues read, without a preview step. Recorded here so
the decision has an owner and a place to be revisited.

**Everything in the room reaches the agent.** No filtering, also requested. The
cost is context: a busy room with webhook traffic adds up over a session. The
`text` field mitigates it by keeping each event to one line instead of a JSON
block, but it does not remove it.

## Out of scope

Socket authentication, multiple Matrix accounts, protocol version negotiation,
and any filtering or summarisation of room traffic.
