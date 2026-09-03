# Troubleshooting

What the error means and what to run. `matrix-doctor.py` decides most of these
without guessing:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install
```

## Errors

| Error | What it is | Fix |
|-------|-----------|-----|
| `M_FORBIDDEN` | not in the room | join it in Element first |
| `M_UNKNOWN_TOKEN` / HTTP 401 | the config token expired or was revoked — `matrix-doctor.py` reports `[FAIL] token` | mint a new one for the skill via `matrix-e2ee-setup.py`; **do not** copy a token out of Element |
| `M_LIMIT_EXCEEDED` | rate limited | wait, retry |
| `Could not find room` | name/alias did not resolve | `matrix-rooms.py` to list what you are in |
| `Room not found` **on a room you are in** | the E2EE credential is dead — a rejected token yields an empty joined-rooms list, which looks like the room is gone. `matrix-doctor.py` reports `[FAIL] e2ee_setup` | re-run `matrix-e2ee-setup.py` |
| `[Unable to decrypt]` | keys for those messages are not in this device's store | first `matrix-fetch-keys.py ROOM --sync-time 60` (asks other devices, no recovery key needed); only then `matrix-key-backup.py --recovery-key "…" --import-keys` |
| `signature failed` | running on a foreign device | dedicated device via `matrix-e2ee-setup.py` |
| `Invalid password` | special characters eaten by the shell | `MATRIX_PASSWORD="pass" uv run …` |
| `libolm not found` | missing native dependency | Linux: `apt install libolm-dev`; macOS 26+ is unsupported, see `setup-guide.md` |
| `matrix-nio not found` | Python dependency missing | `python3 …/matrix-doctor.py --install` |
| `The E2EE store cannot be opened by the installed matrix-nio (0.25.x)` | **backend mismatch, not a broken store**: the store was written by nio ≥ 0.26 (vodozemac format), the installed nio is < 0.26 (libolm), or the reverse. The error says so in its first lines — read them before claiming the store is defective | pin nio to the version that wrote the store, or re-create the device with `matrix-e2ee-setup.py` and re-import keys |

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
# 1. transport
uv run $C/matrix-watchd.py --status      # or --start

# 2. the gap it was down for — this is the step that gets skipped
uv run $C/matrix-read-e2ee.py ROOM --limit 50
```

Read back to the last message you actually saw, not to the last message the
daemon logged: those differ by exactly the outage.

**Liveness is not a one-time check.** A daemon that was running an hour ago
tells you nothing now. Before reporting anything as "no news from the room", ask
its status in the same breath — silence from a dead watcher looks identical to
silence from a quiet room, and only one of them is true.

## "No access" is a claim about you, not about the service

Three times in one session this skill's transport was reported as unreachable
and the work parked. All three were self-inflicted: a stale token in
`config.json` while a working one sat in the skill's own store, a wrong path,
and one that was never tried at all.

Before saying a room, a token or the homeserver is unavailable:

```bash
python3 $C/matrix-doctor.py            # what the skill itself thinks is wrong
uv run $C/matrix-e2ee-setup.py --status
```

`matrix-doctor.py` reads the credentials the skill stores; a token rejected from
`~/.config/matrix/config.json` while the store holds a working one is a stale
config, not a lost credential — and the fix is a repair, not a new token. Say
"I have not got access" only after the tool has said so too.

## Mistakes that cost the most time

**Calling the store "broken" from the tail of an error.** A session in 2026-08 read
the last line of the store error, matched it against an old memory note and reported
the E2EE store as defective — the message had named the real cause (nio 0.25 cannot
read a vodozemac store) in its first two lines, and the user had already fixed exactly
that once. Before any such claim: read the whole error; then measure on a **copy** of
the store which nio opens it (`uv run --with "matrix-nio==0.25.2" … --status` vs
`--with "matrix-nio>=0.26"`); only then say which side is wrong. A store that one
version opens is not broken.


- **Reusing a running client's access token.** The one mistake here that damages
  something outside this skill — it hijacks that client's device and breaks
  decryption *in that client*, silently, and nothing fails at the moment you
  paste. `SKILL.md` carries the full reasoning; `matrix-e2ee-setup.py` mints a
  device of its own.
- **Using a non-E2EE script in an encrypted room.** Always `*-e2ee.py` unless the
  room is confirmed unencrypted.
- **Forgetting `set +H`** when the message contains `!`.
- **Restoring keys without `--import-keys`** — they are displayed, not stored.
- **Verifying with Element X** — its flow is incompatible; use Element Desktop or
  Android.
- **Passing a password as an argument** instead of `MATRIX_PASSWORD`.
