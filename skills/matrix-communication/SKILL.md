---
name: matrix-communication
description: "Use when communicating via Matrix chat, notifying teams, or managing E2EE. Triggers on #room:server references, Matrix URLs, and chat requests."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python3, uv. Matrix homeserver access."
metadata:
  author: Netresearch DTT GmbH
  version: "1.24.0"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(python3:*) Bash(uv:*) Read Write
---

# Matrix Communication

Matrix rooms: send, read, download media. **Always use `*-e2ee.py` scripts.**

**Bash `!` rule:** Prepend `set +H &&` when arguments contain `!`

## Quick Reference

ROOM: name (`test`), ID (`!abc:server`), or alias (`#room:server`).

```bash
# Send (E2EE)
set +H && uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "message" --no-prefix
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "is deploying" --emote
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "📦 Release: …" --notice    # unattended automation; no auto-reply loops
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --thread '$rootEventId'
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-send-e2ee.py ROOM "reply" --reply '$eventId'

# Read (E2EE) — JSON includes media URL/info for m.image/m.file/m.video/m.audio
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 10
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-read-e2ee.py ROOM --limit 20 --json

# Download media (E2EE) — decrypts and saves by event ID
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-download-e2ee.py ROOM '$eventId' --output /tmp

# Edit / Delete / React
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-redact.py ROOM '$eventId' "reason"
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-react.py ROOM '$eventId' "✅"

# Rooms
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-rooms.py --search ops
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-resolve.py "#room:server"

# E2EE management
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py --status
MATRIX_PASSWORD="pass" uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --timeout 180
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-fetch-keys.py ROOM --sync-time 60
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --recovery-key "EsTj ..." --import-keys

# Health check (uses python3, not uv run)
python3 ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install
```

## Script Selection

| Operation | E2EE (preferred) | Non-E2EE Fallback |
|-----------|-----------------|-------------------|
| Send | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| Download | `matrix-download-e2ee.py` | — |
| React | `matrix-react.py` | (same) |
| Delete | `matrix-redact.py` | (same) |

Other: `matrix-rooms.py`, `matrix-resolve.py`, `matrix-e2ee-setup.py`, `matrix-e2ee-verify.py`, `matrix-fetch-keys.py`, `matrix-key-backup.py`, `matrix-doctor.py`.

## Config

`~/.config/matrix/config.json` — required: `homeserver`, `user_id`. Optional: `access_token`

## Error Handling

| Error | Solution |
|-------|----------|
| `M_FORBIDDEN` | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Get new token from Element |
| `M_LIMIT_EXCEEDED` | Wait and retry |
| `Could not find room` | `matrix-rooms.py` to list rooms |
| `[Unable to decrypt]` | First: `uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-fetch-keys.py ROOM --sync-time 60` (requests keys from other devices, no recovery key needed); fallback: `uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --recovery-key "..." --import-keys` |
| `libolm not found` | `apt install libolm-dev` / `brew install libolm` |
| `matrix-nio not found` | `python3 ${CLAUDE_SKILL_DIR}/scripts/matrix-doctor.py --install` |
| `Invalid password` | Use env var: `MATRIX_PASSWORD="pass" uv run ...` |
| `signature failed` | Dedicated device via `matrix-e2ee-setup.py` |

## Common Mistakes

- **Using non-E2EE scripts** for encrypted rooms — always use `*-e2ee.py`
- **Forgetting `set +H`** — `!` in messages gets mangled by bash
- **Skipping `--import-keys`** — key backup doesn't save without it
- **Using Element X** for verification — use Element Desktop or Android
- **Hardcoding passwords** — use `MATRIX_PASSWORD` env var

## References

- `references/setup-guide.md` — setup
- `references/e2ee-guide.md` — E2EE, key recovery, verification
- `references/messaging-guide.md` — formatting, reactions
- `references/api-reference.md` — Matrix API
- [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
