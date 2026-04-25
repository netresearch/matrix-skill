# Matrix Skill

AI agent plugin shipping two Matrix skills:

- **matrix-communication** — send / read / edit / react in chat rooms as a regular user, with full E2EE support (uses `python-matrix-nio` via `uv`).
- **matrix-administration** — Synapse homeserver operations: snapshot rooms, rate health, render Graphviz map, force-join, promote, harden, deactivate, search history (stdlib-only).

Packaged as a Claude Code plugin following the [Agentic Skills specification](https://agentskills.io).

## Repo Structure

```
skills/matrix-communication/   # Client-Server API, E2EE chat (uses python-matrix-nio via uv)
  SKILL.md, scripts/{_lib, matrix-*-e2ee.py, matrix-*.py, matrix-doctor.py}, references/, evals/

skills/matrix-administration/  # Synapse Admin API, server ops (stdlib-only Python)
  SKILL.md, scripts/{_lib, synapse-*.py}, references/, evals/

commands/work-update.md   # /work-update slash command template
.claude-plugin/plugin.json   # Plugin manifest — lists both skills
docs/ARCHITECTURE.md
Build/Scripts/   # CI validation
scripts/verify-harness.sh   # Harness maturity checker
.github/workflows/   # lint, release, harness-verify, auto-merge-deps, eval-validate
```

## Commands — matrix-communication

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

## Commands — matrix-administration

Stdlib-only Python; run via `python3`. See [`skills/matrix-administration/SKILL.md`](skills/matrix-administration/SKILL.md) for the full quick reference. Most-used:

```bash
S=skills/matrix-administration/scripts
python3 $S/synapse-fetch-rooms.py                       # snapshot → rooms.json
python3 $S/synapse-rate-rooms.py --space '!home:srv'    # health checks
python3 $S/synapse-graph.py --space '!home:srv'         # → rooms.svg
python3 $S/synapse-deactivate-user.py '@user:srv'       # DESTRUCTIVE
python3 $S/synapse-migrate-room.py '!room:srv' '@admin:srv' '!home:srv'   # harden
```

## Rules — matrix-administration

- **Admin token required**: All `synapse-*` scripts read `~/.config/matrix/config.json` and need `admin_token` (preferred) or `access_token` of a Synapse server-admin.
- **No homeserver-specific defaults baked in**: pass `--space` / `--server` on the CLI or set `home_space_ids` / `room_filter` / `default_space_id` in the config.
- **Surface destructive ops** before running: `synapse-deactivate-user.py` (irreversible) and `synapse-migrate-room.py` (encryption is one-way). Never silently pass `--yes`.
- **Local vs live**: `synapse-rate-rooms.py`, `synapse-graph.py`, `synapse-user-*-rooms.py` read `rooms.json` — re-run `synapse-fetch-rooms.py` if stale.
- **Never commit** `rooms.json` / `rooms.dot` / `rooms.svg` — they expose every indexed room.
- **E2EE search caveat**: `synapse-search.py` only sees plaintext; tell the user that empty results ≠ no messages.

## Rules — matrix-communication

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

### matrix-communication
- [SKILL.md](skills/matrix-communication/SKILL.md) — skill definition and quick reference
- [Setup Guide](skills/matrix-communication/references/setup-guide.md)
- [E2EE Guide](skills/matrix-communication/references/e2ee-guide.md)
- [Messaging Guide](skills/matrix-communication/references/messaging-guide.md)
- [API Reference](skills/matrix-communication/references/api-reference.md)

### matrix-administration
- [SKILL.md](skills/matrix-administration/SKILL.md) — skill definition and quick reference
- [Synapse Admin API endpoints](skills/matrix-administration/references/synapse-admin-api.md)
- [Room health checks](skills/matrix-administration/references/room-health-checks.md)
- [Room graph pipeline](skills/matrix-administration/references/room-graph-pipeline.md)
- [Safety guide](skills/matrix-administration/references/safety-guide.md)

### Repo
- [Architecture](docs/ARCHITECTURE.md) — system design and distribution
- [Source](https://github.com/netresearch/matrix-skill)
