# Matrix Skill

AI agent skill for Matrix chat communication: send/read/edit messages, E2EE encryption, reactions, threads, and room management. Packaged as a Claude Code plugin following the [Agentic Skills specification](https://agentskills.io).

## Repo Structure

```
skills/matrix-communication/
  SKILL.md              # Skill entry point -- agent reads this first
  scripts/              # Python scripts for each Matrix operation
    _lib/               # Shared library (config, http, rooms, formatting, e2ee, utils)
    matrix-*-e2ee.py    # E2EE variants (send, read, edit) -- ALWAYS prefer these
    matrix-*.py         # Non-E2EE fallbacks + standalone tools (react, redact, rooms, resolve)
    matrix-doctor.py    # Health check / dependency installer
  references/           # Detailed guides (setup, e2ee, messaging, api)
  evals/                # Skill evaluation definitions
commands/work-update.md # /work-update slash command template
.claude-plugin/plugin.json  # Claude Code plugin manifest
docs/ARCHITECTURE.md    # System architecture overview
Build/Scripts/          # CI validation scripts (version checks)
scripts/verify-harness.sh   # Harness maturity checker
.github/workflows/      # CI: lint, release, harness-verify, auto-merge-deps
```

## Commands

All scripts live in `skills/matrix-communication/scripts/`. Use `uv run` unless noted.

```bash
# Send (always prefer E2EE)
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "message"
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "text" --thread '$rootEventId'
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "text" --reply '$eventId'
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "acting" --emote
set +H && uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "text" --no-prefix

# Read
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM --limit 10
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM --limit 20 --json

# Edit / Delete
set +H && uv run skills/matrix-communication/scripts/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run skills/matrix-communication/scripts/matrix-redact.py ROOM '$eventId' "reason"

# React
uv run skills/matrix-communication/scripts/matrix-react.py ROOM '$eventId' "✅"

# Rooms
uv run skills/matrix-communication/scripts/matrix-rooms.py
uv run skills/matrix-communication/scripts/matrix-rooms.py --search ops
uv run skills/matrix-communication/scripts/matrix-resolve.py "#room:server"

# E2EE management
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py           # Initial device setup
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py --status  # Check setup status
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --timeout 180  # SAS verification
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py ROOM --sync-time 60  # Fetch missing keys
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj ..." --import-keys  # Restore backup

# Health check (uses python3 directly, not uv run)
python3 skills/matrix-communication/scripts/matrix-doctor.py --install

# Harness verification
bash scripts/verify-harness.sh --status
```

## Rules

**E2EE first**: Always use `*-e2ee.py` scripts. Only fall back to non-E2EE if the room is confirmed unencrypted.

**Room identifiers**: Scripts accept three formats -- short name (`agent-work`), room alias (`#room:server`), or room ID (`!abc:server`). Use `matrix-rooms.py` to discover available rooms.

**Config**: Located at `~/.config/matrix/config.json`. Required fields: `homeserver`, `user_id`. Optional: `access_token` (for non-E2EE scripts), `bot_prefix`.

**Running scripts**: Use `uv run` for all scripts except `matrix-doctor.py` which uses `python3` directly (it bootstraps dependencies).

**Bash `!` handling**: Always prepend `set +H &&` before commands containing `!` in messages. Bash history expansion corrupts exclamation marks otherwise.

**Passwords with special chars**: Pass via env var, not CLI arg: `MATRIX_PASSWORD="p@ss!" uv run ...`

**Key backup**: Always include `--import-keys` flag when restoring. Without it, keys are displayed but not saved to the local store.

**Device verification**: Use Element Desktop or Element Android to verify the agent's device. Element X has incompatible verification flows.

**Line buffering**: Scripts use `line_buffering=True` for non-interactive (piped) contexts. Output appears in real time.

**First E2EE run**: Takes ~2-5 seconds for initial key sync. Subsequent runs are faster.

**Dependencies**: Requires `python3`, `uv`, Matrix homeserver access. E2EE scripts additionally need `libolm-dev` (apt) / `libolm-devel` (dnf) / `libolm` (brew).

## Testing

Use the `#test` room (or a room named `test`) for all testing. Never test in production rooms. Send a message and verify it appears in Element to confirm E2EE works end-to-end.

## References

- [SKILL.md](skills/matrix-communication/SKILL.md) -- skill definition and quick reference
- [Setup Guide](skills/matrix-communication/references/setup-guide.md) -- initial configuration walkthrough
- [E2EE Guide](skills/matrix-communication/references/e2ee-guide.md) -- encryption, key recovery, verification
- [Messaging Guide](skills/matrix-communication/references/messaging-guide.md) -- formatting, reactions, threads
- [API Reference](skills/matrix-communication/references/api-reference.md) -- Matrix API endpoints
- [Architecture](docs/ARCHITECTURE.md) -- system design and distribution
- [Source](https://github.com/netresearch/matrix-skill)
