<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Troubleshooting

What the error means and what to run. `matrix-doctor.py` decides most of these
without guessing:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install
```

## Errors

| Error | What it is | Fix |
|-------|-----------|-----|
| `M_FORBIDDEN` | not in the room | join it in Element first |
| `M_UNKNOWN_TOKEN` / HTTP 401 | a token expired or was revoked — `matrix-doctor.py` reports `[FAIL] e2ee_setup` for the skill's device, `[FAIL] token` for an `admin_token` | for the device, `matrix-e2ee-setup.py --force`; for an `admin_token`, a new server-admin token (or remove it, and the `synapse-*` scripts use the device's); **do not** copy a token out of Element |
| `M_LIMIT_EXCEEDED` | rate limited | wait, retry |
| `Could not find room` | name/alias did not resolve | `matrix-rooms.py` to list what you are in |
| `'NAME' matches several rooms: …` / `no joined room matches 'NAME'` / `'NAME' is only part of the name of …` | a script looked the short name up (alias before one exact display name, as the E2EE scripts of version 4 did) and found several rooms, none, or (for send, edit, react, redact, invite, `power-level --set`) only a partial match; nothing was sent | pass the room ID or the full alias (`#name:server`) from the list in the message or from `matrix-rooms.py` |
| `Room not found` **on a room you are in** | the E2EE credential is dead — a rejected token yields an empty joined-rooms list, which looks like the room is gone. `matrix-doctor.py` reports `[FAIL] e2ee_setup` | `matrix-e2ee-setup.py --force` (without `--force` it keeps the dead session and only shows its state) |
| `[Unable to decrypt]` | keys for those messages are not in this device's store | first `matrix-fetch-keys.py ROOM --sync-time 60` (asks other devices, no recovery key needed); only then `matrix-key-backup.py --recovery-key --import-keys` (prompts for the key) |
| `signature failed` | running on a foreign device | dedicated device via `matrix-e2ee-setup.py --force` |
| `Invalid password` | special characters eaten by the shell | `MATRIX_PASSWORD="pass" uv run …` |
| `no matrix-e2ee-cli release for …` | no release binary for this platform | build matrix-e2ee-cli yourself and set `MATRIX_E2EE_CLI` to the binary |
| `downloaded … has SHA-256 …, but the skill pins …` | the downloaded binary is not the pinned release; it was deleted and not run | do not work around it: retry, and report it if it persists |
| `the matrix-nio store … is in use` | the first E2EE command wants to take the old matrix-nio device over (`e2ee-guide.md`, "Moving from matrix-nio"), and a `matrix-watchd.py` or E2EE script of an older version still holds that store | stop that process (the message names the pid when the old daemon answers), then run the command again |
| `migrate-nio failed …` | the takeover of the old device failed; the command did not run, the old store is unchanged and a copy was made | read the `migrate-nio` output above the error. To give the old device up instead, move `~/.local/share/matrix-skill/store` away and run `matrix-e2ee-setup.py` (a new device) |

Two of these look like the same error and are not: `M_UNKNOWN_TOKEN` says the
token is dead, while `Room not found` on a room you are demonstrably in says the
**E2EE credential** is dead. `matrix-doctor.py` distinguishes them, which is
faster than reasoning about it.

## A repaired watcher is not a recovered history

Fixing the transport and reading the room again are two jobs, and doing only the
first leaves a hole exactly where the interesting messages are — the ones sent
while the watcher was down.

Measured in one maintenance window: four colleague messages were identified as
unread, said out loud to be unread, and never fetched. The daemon was restarted,
the room was declared "watched again", and the gap stayed empty for the rest of
the night.

So the recovery is two steps, always:

```bash
# 1. transport — and check the room is in watch_rooms, not just that the daemon runs
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watchd.py --status

# 2. the gap it was down for — this is the step that gets skipped
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 50
```

**A running daemon is not a watched room.** Rooms come from `watch_rooms` in
`~/.config/matrix/config.json`; if this one is not in that list, `--start`
changes nothing — add the room and restart the daemon, then backfill.

Read back to the last message you actually saw, not to the last message the
daemon logged: those differ by exactly the outage. **This read is best-effort
recent history**: `matrix-read-e2ee.py` issues a single `room_messages` request
with no pagination, so a gap longer than `--limit` is silently truncated. Raise
the limit past the number of messages you expect, and if the outage is long
enough that you cannot bound it, say the history is partial rather than
implying it is complete.

**Liveness is not a one-time check.** A daemon that was running an hour ago
tells you nothing now. Before reporting anything as "no news from the room", ask
its status in the same breath — silence from a dead watcher looks identical to
silence from a quiet room, and only one of them is true.

And a dead watcher is not a note for later. Re-arm it in the same turn you
discover it, or say plainly, in that turn, that you are **no longer reading the
room** — those are the only two honest endings, and "I will restart it" is
neither. A watcher that died on its first event and was never replaced left one
session broadcasting into rooms it had stopped listening to for the remaining
nine hours; nothing in the transcript looked wrong, because a watcher that
emits nothing and a room where nothing happens produce the same empty log.

## "No access" is a claim about you, not about the service

Three times in one session this skill's transport was reported as unreachable
and the work parked. All three were self-inflicted: a stale token in
`config.json` while a working one sat in the skill's own store, a wrong path,
and one that was never tried at all.

Before saying a room, a token or the homeserver is unavailable:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py            # what the skill itself thinks is wrong
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py --status
```

`matrix-doctor.py` reads the credential the skill stores (matrix-e2ee-cli's
`session.json`); a token rejected from
`~/.config/matrix/config.json` while the store holds a working one is a stale
config, not a lost credential — and the fix is a repair, not a new token. Say
"I have not got access" only after the tool has said so too.

**The token copies drift apart independently.** The E2EE `session.json` and
`admin_token` in `config.json` each go stale on their own schedule, and which
one is live changes over time. `whoami` each
copy (the `curl` in `setup-guide.md`) before concluding anything about any of
them. A doctor `[FAIL] token` names the label it rejected — a dead `admin_token`
says nothing about sending, which never uses it.

**A dead `admin_token` shadows a live admin session.** The `synapse-*`
scripts use a set admin token (`MATRIX_ADMIN_TOKEN`, `admin_token_file`,
`admin_token`) before the matrix-e2ee-cli session, so a non-empty but revoked
`admin_token` makes every admin call return `401` even when the session's
account is a server admin. The session is never tried. Remove or replace the
dead `admin_token`; do not report "no admin access" before checking the
session's token against an admin endpoint.

## Mistakes that cost the most time

**Calling the store "broken" from the tail of an error.** A session in 2026-08 read
the last line of a store error, matched it against an old memory note and reported
the E2EE store as defective — the message had named the real cause in its first two
lines. Before any such claim, read the whole error.

- **Reusing a running client's access token.** The one mistake here that damages
  something outside this skill — it hijacks that client's device and breaks
  decryption *in that client*, silently, and nothing fails at the moment you
  paste. `SKILL.md` carries the full reasoning; `matrix-e2ee-setup.py` mints a
  device of its own.
- **Forgetting `set +H`** when the message contains `!`.
- **Running `matrix-e2ee-cli.py logout` to retire the old matrix-nio copy** — it
  logs the migrated device out on the server. Delete the old store directory
  instead.
- **Verifying with Element X** — its flow is incompatible; use Element Desktop or
  Android.
- **Passing a password as an argument** instead of `MATRIX_PASSWORD`.
