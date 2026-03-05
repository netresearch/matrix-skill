---
name: matrix-communication
description: "Use when sending messages to Matrix rooms, interacting with Matrix chat, or automating team notifications via Matrix protocol."
---

# Matrix Communication

Send messages to Matrix chat rooms on behalf of users.

## When to Use

Automatically activate when you encounter:
- Room references: `#room:server`, `!roomid:server`
- Chat requests: "send to matrix", "post in chat", "notify the team"
- Matrix URLs: `https://matrix.*/`, `https://element.*/`
- Setup requests: "configure matrix", "set up matrix skill"

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

Other scripts: `matrix-rooms.py` (list rooms), `matrix-resolve.py` (alias lookup), `matrix-e2ee-setup.py` (one-time device setup), `matrix-e2ee-verify.py` (device verification), `matrix-fetch-keys.py` / `matrix-key-backup.py` (key recovery).

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

## Reading Room History

- **First run is slow** (~5-10s) due to key sync
- **Old messages** show `[Unable to decrypt]` until keys are recovered (see key backup above)
- Use `--json` for programmatic analysis (reactions, polls, attendance)
- Reactions appear as separate `m.reaction` events — see `references/messaging-guide.md`

## E2EE Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `[Unable to decrypt]` | Missing session keys | Restore from backup: `matrix-key-backup.py --recovery-key "..." --import-keys` |
| Script hangs silently | stdout buffering | Already fixed — scripts use `line_buffering=True` |
| Verification not completing | No `--listen` mode | Run verify with `--timeout 180`, confirm in Element |
| Element X won't verify | Cross-signing compat | Use Element Desktop/Android instead of Element X |
| `MAC verification failed` | Wrong recovery key/passphrase | Double-check recovery key from Element settings |

## Error Handling

| Error | Solution |
|-------|----------|
| `M_FORBIDDEN` | Join room first in Element |
| `M_UNKNOWN_TOKEN` | Get new token from Element |
| `Could not find room` | Use `matrix-rooms.py` to list available rooms |
| `Multiple matches` | Use more specific name or room ID |

## Source & Contributing

- **Source repository**: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
- **Distributed via**: [netresearch/claude-code-marketplace](https://github.com/netresearch/claude-code-marketplace)
- **Issues & PRs**: File at the source repository, not the marketplace

## References

- `references/setup-guide.md` -- Full setup walkthrough (homeserver discovery, E2EE device creation, verification)
- `references/e2ee-guide.md` -- E2EE details, key recovery, device verification workflow
- `references/messaging-guide.md` -- Formatting, reactions, visual effects, common patterns
- `references/api-reference.md` -- Matrix API endpoints
