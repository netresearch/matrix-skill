---
name: matrix-communication
description: "Use when working with ANY Matrix chat operation — sending messages, reading rooms, reacting, thread replies, E2EE messaging, or team notifications via Matrix protocol. Activate on #room:server references or Matrix URLs."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python3, uv. Matrix homeserver access."
metadata:
  author: Netresearch DTT GmbH
  version: "1.16.0"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(python3:*) Bash(uv:*) Read Write
---

# Matrix Communication

Send messages to Matrix chat rooms on behalf of users.

## Quick Reference

```bash
# Send message (E2EE preferred)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py room-name "Hello!"

# Send by room alias
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py "#room:server" "Hello!"

# List joined rooms
uv run skills/matrix-communication/scripts/matrix-rooms.py

# Read recent messages (E2EE)
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py room-name --limit 10

# React to a message
uv run skills/matrix-communication/scripts/matrix-react.py room-name '$eventId' "✅"

# Thread reply
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py room-name "Update" --thread '$rootEventId'

# Emote message (like /me)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py room-name "is deploying" --emote

# Fetch missing keys from other devices
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py room-name --sync-time 60

# Restore keys from server backup (decrypt old messages)
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj ..." --import-keys

# Health check / auto-install deps
python3 skills/matrix-communication/scripts/matrix-doctor.py --install
```

## Scripts Overview

Always prefer E2EE scripts (`*-e2ee.py`) -- most Matrix rooms are encrypted.

| Operation | E2EE Script (preferred) | Non-E2EE Fallback |
|-----------|------------------------|-------------------|
| Send message | `matrix-send-e2ee.py` | `matrix-send.py` |
| Read messages | `matrix-read-e2ee.py` | `matrix-read.py` |
| Edit message | `matrix-edit-e2ee.py` | `matrix-edit.py` |
| React | `matrix-react.py` | (same) |
| Redact | `matrix-redact.py` | (same) |

Other: `matrix-rooms.py`, `matrix-resolve.py`, `matrix-e2ee-setup.py`, `matrix-e2ee-verify.py`, `matrix-fetch-keys.py`, `matrix-key-backup.py`.

## Room Identification

| Format | Example | Description |
|--------|---------|-------------|
| Room name | `agent-work` | Easiest -- matched from joined rooms |
| Room ID | `!sZBo...Q22E` | Direct, from `matrix-rooms.py` output |
| Room alias | `#room:server` | Resolved via Matrix directory |

## Config

File: `~/.config/matrix/config.json`

| Field | Required | Description |
|-------|----------|-------------|
| `homeserver` | Yes | Matrix server URL |
| `user_id` | Yes | Full Matrix user ID (`@user:server`) |
| `bot_prefix` | No | Prefix for messages (e.g., bot emoji) |
| `access_token` | No | Auto-created by E2EE setup |

## E2EE Notes

- First run slow (~5-10s) due to key sync. `[Unable to decrypt]` = missing keys, recoverable via key backup
- Use `--json` for programmatic analysis; reactions are `m.reaction` events (see `references/messaging-guide.md`)
- Verify with Element Desktop/Android (not Element X). Use `--timeout 180` for verification

## Error Handling

| Error | Solution |
|-------|----------|
| `M_FORBIDDEN` | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Get new token from Element |
| `Could not find room` | Use `matrix-rooms.py` to list available rooms |
| `Multiple matches` | Use more specific name or room ID |

## References

- `references/setup-guide.md` -- Setup walkthrough
- `references/e2ee-guide.md` -- E2EE details, key recovery, verification
- `references/messaging-guide.md` -- Formatting, reactions, common patterns
- `references/api-reference.md` -- Matrix API endpoints
- Source: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
