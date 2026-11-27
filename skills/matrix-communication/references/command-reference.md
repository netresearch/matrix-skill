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
user ID (`@jane:server`). Resolving such names costs one request per unnamed
room on the paths that do not sync.

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
- In an encrypted room the message key goes to verified devices only. If the
  room has unverified devices, the send is refused and lists them. Verify them,
  or pass `--trust-unverified-devices` to share this one message's key with
  them anyway; the flag is not remembered and marks no device verified. The
  same flag exists on `matrix-edit-e2ee.py`. Reactions are sent unencrypted,
  so `matrix-react.py` shares no room key and accepts the flag without effect.
- `matrix-react.py` and `matrix-redact.py` run matrix-e2ee-cli's `react` and
  `redact` with the skill's E2EE device, like the `*-e2ee.py` scripts; an
  `access_token` in the config is not enough for them.

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
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py --lookup "Jane Doe"   # direct chat by name
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-resolve.py "#room:server"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-create-room.py "Room Name" --alias localpart --invite '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-invite.py ROOM '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-power-level.py ROOM --show
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-power-level.py ROOM --set '@user:server' 50
```

Run `--show` before `--set` on any room you did not create — see
`api-reference.md` for what the levels mean.

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
  `--force` replaces a dead or foreign device with a new one.
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
rather than OK.

## Script selection

| Operation | E2EE (preferred) | Non-E2EE fallback |
|-----------|-----------------|-------------------|
| Send | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| Download | `matrix-download-e2ee.py` | — |
| React | `matrix-react.py` | — |
| Delete | `matrix-redact.py` | — |

Fall back to the non-E2EE scripts only for a room confirmed to be unencrypted. The one exception is a bot command to a bridge that does not decrypt (see [hookshot-integration.md](hookshot-integration.md)), and only for content you are fine to disclose to the homeserver.

## Config

`~/.config/matrix/config.json`

| Key | |
|---|---|
| `homeserver` | required |
| `user_id` | required |
| `access_token` | optional, **non-E2EE scripts only** |
| `access_token_file` | optional: path to a file holding `access_token` (relative to the config directory), so the token stays out of `config.json` |
| `watch_rooms` | rooms `matrix-watchd.py` logs |
| `bot_prefix` | message prefix |

`MATRIX_ACCESS_TOKEN` in the environment overrides `access_token_file`, which
overrides `access_token` (`_lib/config.py`, `resolve_tokens`). Rotating the
token means replacing that one value; the rest of `config.json` stays as it is.

Copy `access_token` from the skill's own session, matrix-e2ee-cli's
`session.json` (setup-guide, step 6) — never from a client you use. The reason is in `SKILL.md`, and it is the one
mistake in this skill that damages something outside it.
