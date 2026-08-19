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

Two of these look like the same error and are not: `M_UNKNOWN_TOKEN` says the
token is dead, while `Room not found` on a room you are demonstrably in says the
**E2EE credential** is dead. `matrix-doctor.py` distinguishes them, which is
faster than reasoning about it.

## Mistakes that cost the most time

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
