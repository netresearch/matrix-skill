# Command Reference

Every script in this skill, with the flags that are not obvious from `--help`.
`SKILL.md` carries only the handful used in almost every session; this is the
full surface.

`ROOM` is a short name (`test`), a room ID (`!abc:server`) or an alias
(`#room:server`) everywhere below.

**Prepend `set +H &&` whenever an argument contains `!`** — bash history
expansion mangles it otherwise, and the corruption is silent.

## Send

```bash
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message"
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "text" --mention '@user:server'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message" --no-prefix
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "is deploying" --emote
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "📦 Release: …" --notice
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --thread '$rootEventId'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --reply '$eventId'
```

- `--mention` is what notifies. A plain `@name` in the text notifies nobody —
  only `m.mentions` does. `--mention-room` for `@room`.
- `--notice` sends `m.notice`, which other bots do not auto-reply to. Use it for
  unattended automation; mutually exclusive with `--emote`.

## Read, download, edit, delete, react

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 10
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 20 --json
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-download-e2ee.py ROOM '$eventId' --output /tmp
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-redact.py ROOM '$eventId' --reason "reason"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "✅"
```

`--json` output includes the media URL and info for `m.image` / `m.file` /
`m.video` / `m.audio` events; `matrix-download-e2ee.py` decrypts and saves by
event ID.

## Live awareness

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watchd.py --start | --status | --stop
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watch.py ROOM [--cursor NAME] [--once]
```

The daemon owns the store for its whole run; everything else routes through it.

## Rooms and membership

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py --search ops
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
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --listen --timeout 180
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --list
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-fetch-keys.py ROOM --sync-time 60
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --recovery-key "EsTj …" --import-keys
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --import-keys
```

- Pass the password through `MATRIX_PASSWORD`, never as an argument — special
  characters do not survive the shell.
- `--listen` lets Element initiate; prefer it over `--request` when several
  sessions exist. Use Element Desktop or Android — Element X has an incompatible
  verification flow.
- `--import-keys` is what stores restored keys. Without it they are displayed and
  lost.

## Health check

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install
python3 ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --offline
```

`matrix-doctor.py` runs under `python3`, not `uv run` — it bootstraps the
dependencies the others need. `--offline` skips the homeserver call, and the
token row then reads `not verified` rather than OK.

## Script selection

| Operation | E2EE (preferred) | Non-E2EE fallback |
|-----------|-----------------|-------------------|
| Send | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| Download | `matrix-download-e2ee.py` | — |
| React | `matrix-react.py` | (same) |
| Delete | `matrix-redact.py` | (same) |

Fall back to the non-E2EE scripts only for a room confirmed to be unencrypted.

## Config

`~/.config/matrix/config.json`

| Key | |
|---|---|
| `homeserver` | required |
| `user_id` | required |
| `access_token` | optional, **non-E2EE scripts only** |
| `watch_rooms` | rooms `matrix-watchd.py` logs |
| `bot_prefix` | message prefix |

Copy `access_token` from the skill's own `credentials.json` (setup-guide, step
6) — never from a client you use. The reason is in `SKILL.md`, and it is the one
mistake in this skill that damages something outside it.
