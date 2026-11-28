<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Command Reference

Every script in this skill, with the flags that are not obvious from `--help`.
`SKILL.md` carries only the handful used in almost every session; this is the
full surface.

`ROOM` is a short name (`test`), a room ID (`!abc:server`), an alias
(`#room:server`) or a `https://matrix.to/#/…` link copied from Element
everywhere below. A room without a name — a direct chat, usually — goes by
the name Element shows for it: the other person's display name, or their
user ID (`@jane:server`). A short name, also `#name` without the server, is
looked up among the joined rooms `matrix-e2ee-cli rooms --json` lists (from
the CLI's store, or from the watch daemon while it runs), in the order the
E2EE scripts of version 4 used: alias without server, then a single exact display name (one
exact name wins even when other names contain it), then a single partial
match. `matrix-react.py` and `matrix-redact.py` now follow that order too;
in version 4 they refused an exact name that another room's name contained.
So do `matrix-send.py`, `matrix-read.py`, `matrix-edit.py`,
`matrix-invite.py` and `matrix-power-level.py`: in version 5.0.0 they refused
an exact name of a room without alias when another room's name contained it
(`test` beside `test-archive`), and took the first of several rooms with the
same alias name, which is now refused. `matrix-rooms.py --lookup` keeps the
rule of version 5.0.0 (matrix-e2ee-cli's `rooms --lookup`), and it may return a
single partial match: pass the name itself to a command that writes, which
looks it up with the stricter rule.
A listing that fails, or a room whose members the CLI could not read, stops
the command. Only this lookup of the scripts that take a ROOM stops there:
`matrix-rooms.py --lookup` and `--search` print the warning and still
answer, so their result is no proof that the listing was complete. Without a
matrix-e2ee-cli session a short name stops the command too (run
`matrix-e2ee-setup.py`); on a machine with a matrix-nio device the takeover
runs first and creates the session. Send, edit, react, redact, invite and `power-level --set`
accept only an exact alias or exact name: anyone who
can name a room you are in could otherwise steer a partial match. A name
that matches several rooms, or none, stops the command before anything is
sent. A room ID or full alias goes to matrix-e2ee-cli unchanged, without the
lookup.

**Prepend `set +H &&` whenever an argument contains `!`** — bash history
expansion mangles it otherwise, and the corruption is silent.

## Send

```bash
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message"
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "text" --mention '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message" --no-prefix   # bot commands (!hookshot …) need it when bot_prefix is set; see hookshot-integration.md for encrypted rooms
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "is deploying" --emote
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "📦 Release: …" --notice
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --thread '$rootEventId'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --reply '$eventId'
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py --to '@user:server' "message"
```

- `--to @user:server` replaces `ROOM` and sends to the existing direct chat
  with that person. Where `ROOM` finds a direct chat by the name it is shown
  under, `--to` reads the account data `m.direct`, which marks it as direct
  even when it has a name or the person is in other rooms with you. That list
  keeps rooms after a leave, so a room counts only when you are joined and
  the other person is joined or invited. No usable room, or more than one, is
  an error that names the rooms — `--to` never creates a room, and with
  several it does not guess: pass the room ID.

- `--mention` is what notifies. A plain `@name` in the text notifies nobody —
  only `m.mentions` does. `--mention-room` for `@room`.
- `--notice` sends `m.notice`, which other bots do not auto-reply to. Use it for
  unattended automation; mutually exclusive with `--emote`.
- `--plaintext` (also on `matrix-send.py`) sends this one message unencrypted,
  also in an encrypted room; the homeserver and everyone who joins later can
  read it. Only for a bot that cannot decrypt, such as a hookshot bridge
  without encryption (`hookshot-integration.md`). Mutually exclusive with
  `--trust-unverified-devices`.
- In an encrypted room the message key goes to verified devices only. If the
  room has unverified devices, the send is refused and lists them. Verify them,
  or pass `--trust-unverified-devices` to share this one message's key with
  them anyway; the flag is not remembered and marks no device verified. The
  same flag exists on `matrix-edit-e2ee.py`. Reactions are sent unencrypted,
  so `matrix-react.py` shares no room key and accepts the flag without effect.
- Every script except `matrix-doctor.py` runs a matrix-e2ee-cli command with
  the skill's E2EE device; none reads a token from the config.

## Read, download, edit, delete, react

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 10
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 20 --json
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-download-e2ee.py ROOM '$eventId' --output ./downloads   # never replaces an existing file
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-redact.py ROOM '$eventId' --reason "reason"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "✅"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "▶️" "🤖"   # several in one call, in order
# status swap: set ✅, remove this account's own ▶️/🩹 on that event (looked up, no id needed)
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "✅" --replace "▶️" "🩹"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "▶️" --remove
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' --list   # own reactions, changes nothing
```

`--json` output carries `format` and `formatted_body` next to `body` when the
event has them. `body` is only the plain-text fallback and can differ from what
Element shows: a hookshot webhook message without a `text` key has
`Received webhook data:` plus the raw JSON in `body` and the rendered HTML in
`formatted_body` (see `hookshot-integration.md`). Judge how a message renders
from `formatted_body`, never from `body` alone.

`--json` output includes the media URL and info for `m.image` / `m.file` /
`m.video` / `m.audio` events; `matrix-download-e2ee.py` decrypts and saves by
event ID. It refuses to replace an existing file of the same name (pass
`--filename` or another `--output`; `--overwrite` is not supported any more).

## Live awareness

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watchd.py --start | --status | --stop
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watch.py ROOM [--cursor NAME] [--once]
```

The daemon (`matrix-e2ee-cli watch-daemon`) owns the store for its whole run;
the E2EE send, edit, react and redact of the CLI route through it.
`matrix-watch.py` takes a room ID, or the alias or name as written in
`watch_rooms`.

## Rooms and membership

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py --search ops
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py --lookup "Jane Doe"   # room ID of the direct chat, to read; never feed it to a write
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-resolve.py "#room:server"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-create-room.py "Room Name" --alias localpart --invite '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-invite.py ROOM '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-power-level.py ROOM --show
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-power-level.py ROOM --set '@user:server' 50
```

They run matrix-e2ee-cli's `rooms`, `resolve`, `create-room`, `invite` and
`power-level` with the same flags and output. Run `--show` before `--set` on
any room you did not create — see `api-reference.md` for what the levels
mean.

## E2EE

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py --status
MATRIX_PASSWORD="pass" uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --request DEVICE --timeout 180
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --listen --timeout 180   # own devices only
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --list
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-cli.py verify --listen --hand-over   # no terminal: see e2ee-guide.md
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-fetch-keys.py ROOM --sync-time 60
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --import-keys   # prompts; or MATRIX_RECOVERY_KEY / MATRIX_RECOVERY_PASSPHRASE
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-cli.py COMMAND [ARGS]   # any other matrix-e2ee-cli command
```

The E2EE scripts run [matrix-e2ee-cli](https://github.com/netresearch/matrix-e2ee-cli),
downloaded on first use and checked against the SHA-256 pinned in
`scripts/_lib/cli_release.json` (`MATRIX_E2EE_CLI=/path` uses your own binary).
The first E2EE command on a machine with a matrix-nio store of version 4 or
older takes that device over once (`e2ee-guide.md`, "Moving from matrix-nio").

- Pass the password through `MATRIX_PASSWORD`, never as an argument — special
  characters do not survive the shell.
- `--listen` lets Element initiate; prefer it over `--request` when several
  sessions exist. Use Element Desktop or Android — Element X has an incompatible
  verification flow.
- `--import-keys` is what restores the keys; without it (or `--status`) the
  script refuses.
- `matrix-e2ee-verify.py` needs `--request`, `--listen` or `--list`, and a
  terminal for the first two; an agent uses `verify --hand-over` (e2ee-guide.md).
- `matrix-e2ee-setup.py` keeps an existing session and shows its state;
  `--force` replaces a dead or foreign device with a new one. On a machine
  still on matrix-nio the takeover runs first, so `--force` then replaces the
  device just taken over.
- `matrix-e2ee-setup.py --logout` is refused: `matrix-e2ee-cli.py logout` also
  ends the device on the server.

## Health check

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --offline
```

`matrix-doctor.py` runs under `uv run` like the other scripts and declares no
dependency. Its `e2ee_cli` row checks the pinned matrix-e2ee-cli binary (or
`MATRIX_E2EE_CLI`); `--install` downloads it. `--offline` skips the homeserver
calls and the download, and the token and E2EE rows then read `not verified`
rather than OK. `e2ee_setup` is required: a missing or rejected session
fails the doctor (exit 1, also with `--json`), because every script needs it;
`--offline` or a pending takeover leaves it unchecked, which fails nothing.

## Script selection

| Operation | E2EE (preferred) | Older options, same command |
|-----------|-----------------|-----------------------------|
| Send | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| Download | `matrix-download-e2ee.py` | — |
| React | `matrix-react.py` | — |
| Delete | `matrix-redact.py` | — |

`matrix-send.py`, `matrix-read.py` and `matrix-edit.py` run the same matrix-e2ee-cli commands as their `-e2ee` siblings: encrypted in an encrypted room, unencrypted in an unencrypted one. They keep their older options and lack the newer ones (`--to`, `--mention`, `--trust-unverified-devices`, `--request-keys`). `matrix-send.py --format text` is refused: the CLI always renders Markdown. `matrix-read.py` prints the messages newest first, in the format of `matrix-read-e2ee.py`.

## Config

`~/.config/matrix/config.json`

| Key | |
|---|---|
| `homeserver` | required |
| `user_id` | required |
| `watch_rooms` | rooms `matrix-watchd.py` logs |
| `bot_prefix` | message prefix |

No script reads `access_token`, `access_token_file` or `MATRIX_ACCESS_TOKEN`:
every script logs in with the matrix-e2ee-cli session (`session.json`), the
device `matrix-e2ee-setup.py` created. `matrix-doctor.py` warns about a
leftover one; remove it. Never put a token from a client you use anywhere the
skill reads. The reason is in `SKILL.md`, and it is the one mistake in this
skill that damages something outside it.
