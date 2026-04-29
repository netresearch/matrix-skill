<!-- Managed by agent: keep sections and order; edit content, not structure. Last updated: 2026-04-26 -->

# Matrix Skill

**Precedence:** the **closest `AGENTS.md` / `SKILL.md`** to the files you're changing wins. Each skill under `skills/` has its own `SKILL.md` that is authoritative for that skill — read it first.

## Index of scoped AGENTS.md

The skills below each ship their own `SKILL.md` (read it before editing any file in that directory):

- [`skills/matrix-communication/SKILL.md`](skills/matrix-communication/SKILL.md) — chat operations (Client-Server API, E2EE)
- [`skills/matrix-administration/SKILL.md`](skills/matrix-administration/SKILL.md) — homeserver operations (Synapse Admin API)
- [`skills/matrix-announcement/SKILL.md`](skills/matrix-announcement/SKILL.md) — content guidance for structured Matrix announcements

AI agent plugin shipping three Matrix skills:

- **matrix-communication** — send / read / edit / react in chat rooms as a regular user, with full E2EE support (uses `python-matrix-nio` via `uv`).
- **matrix-administration** — Synapse homeserver operations: snapshot rooms, rate health, render Graphviz map, force-join, promote, harden, deactivate, search history (stdlib-only).
- **matrix-announcement** — content guidance for composing scannable, structured Matrix announcements (release notes, digests, heads-ups, postmortems). Defines the HTML subset, type-tag system, glyph rules, and when to render an HTML card to PNG. No scripts — pairs with `matrix-communication` for delivery.

Packaged as a Claude Code plugin following the [Agentic Skills specification](https://agentskills.io).

## Repo Structure

```
skills/matrix-communication/   # Client-Server API, E2EE chat (uses python-matrix-nio via uv)
  SKILL.md, scripts/{_lib, matrix-*-e2ee.py, matrix-*.py, matrix-doctor.py}, references/, evals/

skills/matrix-administration/  # Synapse Admin API, server ops (stdlib-only Python)
  SKILL.md, scripts/{_lib, synapse-*.py}, references/, evals/

skills/matrix-announcement/    # Content guidance for structured announcements (no scripts)
  SKILL.md, references/{html-subset,structure,glyphs,image-cards,threading,anti-patterns,text-templates}.md
  references/templates/{release-card,weekly-digest,comparison}.html
  references/gallery.html, evals/

commands/work-update.md   # /work-update slash command template
.claude-plugin/plugin.json   # Plugin manifest — lists all three skills
docs/ARCHITECTURE.md
Build/Scripts/   # CI validation
scripts/verify-harness.sh   # Harness maturity checker
.github/workflows/   # lint, release, harness-verify, auto-merge-deps, eval-validate
```

## Commands — matrix-communication

All scripts live in `skills/matrix-communication/scripts/`. Use `uv run` unless noted. `set +H` disables history expansion so `!` in messages survives.

```bash
C=skills/matrix-communication/scripts

# Send (always prefer E2EE) — plain | --thread | --reply | --emote | --notice | --no-prefix
set +H && uv run $C/matrix-send-e2ee.py ROOM "message"
# unattended automation (m.notice — no auto-reply loops; mutex with --emote):
set +H && uv run $C/matrix-send-e2ee.py ROOM "📦 Release: …" --notice

# Read / Edit / React / Redact
uv run $C/matrix-read-e2ee.py ROOM --limit 10 [--json]
set +H && uv run $C/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run $C/matrix-react.py ROOM '$eventId' "✅"
uv run $C/matrix-redact.py ROOM '$eventId' "reason"

# Rooms / aliases
uv run $C/matrix-rooms.py [--search ops]
uv run $C/matrix-resolve.py "#room:server"

# E2EE setup / verify / keys
uv run $C/matrix-e2ee-setup.py [--status]
uv run $C/matrix-e2ee-verify.py --timeout 180
uv run $C/matrix-fetch-keys.py ROOM --sync-time 60
uv run $C/matrix-key-backup.py --recovery-key "EsTj ..." --import-keys

# Health check (python3, not uv run) + harness verification
python3 $C/matrix-doctor.py --install
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

- **E2EE first**: Always use `*-e2ee.py` scripts. Only fall back to non-E2EE if the room is confirmed unencrypted.
- **Room identifiers**: Scripts accept short name (`agent-work`), room alias (`#room:server`), or room ID (`!abc:server`). Use `matrix-rooms.py` to discover.
- **Config**: `~/.config/matrix/config.json` — required: `homeserver`, `user_id`; optional: `access_token` (non-E2EE only), `bot_prefix`.
- **Running scripts**: `uv run` for everything except `matrix-doctor.py` which bootstraps deps via `python3`.
- **Bash `!` handling**: Prepend `set +H &&` before any command whose arguments contain `!` — history expansion corrupts otherwise.
- **Passwords with special chars**: Pass via env var, not CLI arg — `MATRIX_PASSWORD="p@ss!" uv run …`.
- **Key backup**: Always include `--import-keys` when restoring; without it, keys are displayed but not stored.
- **Device verification**: Use Element Desktop or Element Android — Element X has incompatible verification flows.
- **Line buffering** is `True` for non-interactive (piped) contexts; output appears in real time.
- **First E2EE run** takes ~2–5 s for initial key sync; subsequent runs are faster.
- **Dependencies**: `python3`, `uv`, Matrix homeserver access. E2EE additionally needs `libolm-dev` (apt) / `libolm-devel` (dnf) / `libolm` (brew).

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

### matrix-announcement
- [SKILL.md](skills/matrix-announcement/SKILL.md) — five rules + type-tag table + pre-send checklist
- [HTML subset](skills/matrix-announcement/references/html-subset.md)
- [Structure & length budget](skills/matrix-announcement/references/structure.md)
- [Glyphs](skills/matrix-announcement/references/glyphs.md)
- [Image cards (HTML→PNG)](skills/matrix-announcement/references/image-cards.md)
- [Threading, mentions, edits, redactions](skills/matrix-announcement/references/threading.md)
- [Anti-patterns](skills/matrix-announcement/references/anti-patterns.md)
- [Text templates](skills/matrix-announcement/references/text-templates.md)
- [Visual gallery](skills/matrix-announcement/references/gallery.html)

### Repo
- [Architecture](docs/ARCHITECTURE.md) — system design and distribution
- [Source](https://github.com/netresearch/matrix-skill)
