---
name: matrix-communication
description: "Use when needing to communicate via Matrix chat, notify teams, or manage E2EE encryption. Triggers on #room:server references, Matrix URLs, room names, and chat requests."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python3, uv. Matrix homeserver access."
metadata:
  author: Netresearch DTT GmbH
  version: "1.16.0"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(python3:*) Bash(uv:*) Read Write
---

# Matrix Communication

Send and read messages in Matrix rooms via E2EE scripts. Always use `*-e2ee.py` scripts.

**Bash `!` handling:** Prepend `set +H &&` before commands containing `!`.

## Quick Reference

ROOM accepts: name (`test`), ID (`!abc:server`), or alias (`#room:server`).

```bash
# Send (E2EE)
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "message"
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "message" --no-prefix
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "is deploying" --emote
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "reply" --thread '$rootEventId'
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "reply" --reply '$eventId'

# Read (E2EE)
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM --limit 10
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM --limit 20 --json

# Edit / Delete / React
uv run skills/matrix-communication/scripts/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run skills/matrix-communication/scripts/matrix-redact.py ROOM '$eventId' "reason"
uv run skills/matrix-communication/scripts/matrix-react.py ROOM '$eventId' "✅"

# Rooms
uv run skills/matrix-communication/scripts/matrix-rooms.py
uv run skills/matrix-communication/scripts/matrix-rooms.py --search ops
uv run skills/matrix-communication/scripts/matrix-resolve.py "#room:server"

# E2EE management
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py --status
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py ROOM --sync-time 60
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj ..." --import-keys

# Health check (uses python3, not uv run)
python3 skills/matrix-communication/scripts/matrix-doctor.py --install
```

## Script Selection

| Operation | E2EE (preferred) | Non-E2EE Fallback |
|-----------|-----------------|-------------------|
| Send | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| React | `matrix-react.py` | (same) |
| Delete | `matrix-redact.py` | (same) |

Other: `matrix-rooms.py`, `matrix-resolve.py`, `matrix-e2ee-setup.py`, `matrix-e2ee-verify.py`, `matrix-fetch-keys.py`, `matrix-key-backup.py`, `matrix-doctor.py`.

## Config

`~/.config/matrix/config.json` — required: `homeserver`, `user_id`. Optional: `access_token`, `bot_prefix`.

## Error Handling

| Error | Solution |
|-------|----------|
| `M_FORBIDDEN` | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Get new token from Element |
| `M_LIMIT_EXCEEDED` | Wait and retry |
| `Could not find room` | `matrix-rooms.py` to list rooms |
| `[Unable to decrypt]` | `matrix-key-backup.py --recovery-key "..." --import-keys` |
| `libolm not found` | `apt install libolm-dev` / `brew install libolm` |
| `matrix-nio not found` | `python3 skills/matrix-communication/scripts/matrix-doctor.py --install` |
| `Invalid password` | Use env var: `MATRIX_PASSWORD="pass" uv run ...` |
| `signature failed` | Dedicated device via `matrix-e2ee-setup.py` |

## Common Mistakes

- **Using non-E2EE scripts** for encrypted rooms — always default to `*-e2ee.py`
- **Forgetting `set +H`** — `!` in messages/passwords gets mangled by bash
- **Skipping `--import-keys`** — key backup shows but doesn't save keys without it
- **Using Element X** for verification — use Element Desktop or Android
- **Not running `matrix-doctor.py --install`** first — dependency errors

## References

- `references/setup-guide.md` — setup walkthrough
- `references/e2ee-guide.md` — E2EE, key recovery, verification
- `references/messaging-guide.md` — formatting, reactions, patterns
- `references/api-reference.md` — Matrix API endpoints
- Source: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
