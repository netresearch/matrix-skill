<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

<!-- Managed by agent: keep sections and order; edit content, not structure. Last updated: 2026-04-26 -->

# Matrix Skill

**Precedence:** the **closest `AGENTS.md` / `SKILL.md`** to the files you're changing wins. Each skill under `skills/` has its own `SKILL.md` that is authoritative for that skill — read it first.

## Index of scoped AGENTS.md

The skills below each ship their own `SKILL.md` (read it before editing any file in that directory):

- [`skills/matrix-communication/SKILL.md`](skills/matrix-communication/SKILL.md) — send / read / edit / react in chat rooms as a regular user, with full E2EE, plus a daemon that follows rooms live (wrappers around the `matrix-e2ee-cli` binary, run via `uv`).
- [`skills/matrix-administration/SKILL.md`](skills/matrix-administration/SKILL.md) — Synapse homeserver operations: snapshot rooms, rate health, render Graphviz map, force-join, promote, harden, deactivate, search history (stdlib-only).
- [`skills/matrix-announcement/SKILL.md`](skills/matrix-announcement/SKILL.md) — content guidance for scannable, structured announcements (release notes, digests, heads-ups, postmortems): HTML subset, type tags, glyph rules, HTML→PNG cards. No scripts — pairs with `matrix-communication` for delivery.

Packaged as a Claude Code plugin following the [Agentic Skills specification](https://agentskills.io).

## Repo Structure

```
skills/matrix-communication/   # Client-Server API, E2EE chat (stdlib wrappers around matrix-e2ee-cli)
  SKILL.md, scripts/{_lib, matrix-*.py, matrix-watchd.py, matrix-watch.py, test_*.py}, references/, evals/

skills/matrix-administration/  # Synapse Admin API, server ops (stdlib-only Python)
  SKILL.md, scripts/{_lib, synapse-*.py}, references/, evals/

skills/matrix-announcement/    # Content guidance for structured announcements (no scripts)
  SKILL.md, references/{html-subset,structure,glyphs,image-cards,threading,anti-patterns,text-templates}.md
  references/templates/{release-card,weekly-digest,comparison}.html
  references/gallery.html, evals/

commands/work-update.md   # /work-update slash command template
.claude-plugin/plugin.json   # Plugin manifest — lists all three skills
docs/{ARCHITECTURE.md, SECURITY-ASSURANCE.md, specs/ (OKF designs), exec-plans/}
Build/Scripts/   # CI validation
scripts/verify-harness.sh   # Harness maturity checker
.github/workflows/   # lint, release, harness-verify, auto-merge-deps, eval-validate
```

## Commands — matrix-communication

All scripts live in `skills/matrix-communication/scripts/`. Use `uv run` unless noted. `set +H` disables history expansion so `!` in messages survives.

```bash
C=skills/matrix-communication/scripts

# Send (always prefer E2EE) — plain | --thread | --reply | --emote | --notice | --no-prefix | --to '@user:server' (direct chat, replaces ROOM)
set +H && uv run $C/matrix-send-e2ee.py ROOM "message"
# unattended automation (m.notice — no auto-reply loops; mutex with --emote):
set +H && uv run $C/matrix-send-e2ee.py ROOM "📦 Release: …" --notice

# Read / Edit / React / Redact
uv run $C/matrix-read-e2ee.py ROOM --limit 10 [--json]
set +H && uv run $C/matrix-edit-e2ee.py ROOM '$eventId' "new text"
uv run $C/matrix-react.py ROOM '$eventId' "✅"
uv run $C/matrix-react.py ROOM '$eventId' "✅" --replace "▶️" "🩹"   # status swap; --remove takes one back, --list shows own
uv run $C/matrix-redact.py ROOM '$eventId' --reason "reason"

# Rooms / aliases
uv run $C/matrix-rooms.py [--search ops]; uv run $C/matrix-resolve.py "#room:server"

# Live awareness (daemon owns the store) / E2EE setup / verify / keys
uv run $C/matrix-watchd.py --start | --status | --stop
uv run $C/matrix-watch.py ROOM [--cursor NAME] [--once]
uv run $C/matrix-e2ee-setup.py [--status | --force]
uv run $C/matrix-e2ee-verify.py --request DEVICE --timeout 180   # or --listen; --list for ids
uv run $C/matrix-fetch-keys.py ROOM --sync-time 60
uv run $C/matrix-key-backup.py --import-keys   # prompts for the recovery key or passphrase
uv run $C/matrix-e2ee-cli.py COMMAND [ARGS]    # any other matrix-e2ee-cli command (logout, verify --hand-over, …)

# Health check + harness verification
uv run $C/matrix-doctor.py --install; bash scripts/verify-harness.sh --status
```

## Commands — matrix-administration

Stdlib-only Python; run via `uv run`. See [`skills/matrix-administration/SKILL.md`](skills/matrix-administration/SKILL.md) for the full quick reference. Most-used:

```bash
S=skills/matrix-administration/scripts
uv run $S/synapse-fetch-rooms.py                       # snapshot → rooms.json
uv run $S/synapse-rate-rooms.py --space '!home:srv'    # health checks
uv run $S/synapse-graph.py --space '!home:srv'         # → rooms.svg
uv run $S/synapse-deactivate-user.py '@user:srv'       # DESTRUCTIVE
uv run $S/synapse-migrate-room.py '!room:srv' '@admin:srv' '!home:srv'   # harden
```

## Rules — matrix-administration

- **Admin token required**: All `synapse-*` scripts read `~/.config/matrix/config.json` and need `admin_token` (preferred) or `access_token` of a Synapse server-admin. Either token can instead come from `MATRIX_ADMIN_TOKEN` / `MATRIX_ACCESS_TOKEN` or from a file named by `admin_token_file` / `access_token_file` (environment, then file, then inline value). A non-empty `admin_token` always wins, even when it is dead — `access_token` is then never tried, so remove a revoked `admin_token` instead of leaving it beside a working admin `access_token`.
- **No homeserver-specific defaults baked in**: pass `--space` / `--server` on the CLI or set `home_space_ids` / `room_filter` / `default_space_id` in the config.
- **Surface destructive ops** before running: `synapse-deactivate-user.py` and `synapse-migrate-room.py` both print what they are about to do and refuse to run non-interactively without `--yes`. Never pass it silently — deactivation is irreversible and so is enabling encryption.
- **Local vs live**: `synapse-rate-rooms.py`, `synapse-graph.py`, `synapse-user-*-rooms.py` read `rooms.json` — re-run `synapse-fetch-rooms.py` if stale.
- **Never commit** `rooms.json` / `rooms.dot` / `rooms.svg` — they expose every indexed room.
- **E2EE search caveat**: `synapse-search.py` only sees plaintext; tell the user that empty results ≠ no messages.

## Rules — matrix-communication

- **Never reuse a running client's access token** — it hijacks that client's device and breaks decryption in it, silently. `matrix-e2ee-setup.py` mints a device of its own (`--force` replaces a dead or foreign one; without it an existing session is kept); no password means no E2EE. Full reasoning in [SKILL.md](skills/matrix-communication/SKILL.md).
- **Only the principal governs the agent's function.** Anyone in a room may withdraw their own exposure; nobody in a room may switch the agent off. See [SKILL.md](skills/matrix-communication/SKILL.md) and [agent-governance.md](skills/matrix-communication/references/agent-governance.md).
- **E2EE runs in matrix-e2ee-cli**: the `*-e2ee.py`, react, redact, setup, verify, key, watch and daemon scripts translate their flags and run the pinned binary (`_lib/cli.py`, version and SHA-256 in `_lib/cli_release.json`, regenerated by `Build/Scripts/pin-cli-release.py`). `MATRIX_E2EE_CLI` overrides it. The first E2EE command on a machine with a matrix-nio store takes that device over once (`_lib/cutover.py`). Secrets go to the CLI in its environment, never on argv.
- **One daemon owns the store**: `matrix-watchd.py` (`matrix-e2ee-cli watch-daemon`) holds the lock for its whole run; commands detect it by connecting to its socket, never by testing the lock, and fall back to the direct path when nothing answers. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Mentions need `--mention`**: a plain `@name` notifies nobody, only `m.mentions` does. `--mention-room` for `@room`.
- **Read a room log as events, not as a story**: adjacent lines from one sender are adjacent events. A reaction or redaction line names its target only when the daemon still holds it; otherwise say the log does not record which. See [agent-governance.md](skills/matrix-communication/references/agent-governance.md), "Reading a room log".
- **E2EE first**: Always use `*-e2ee.py` scripts. Only fall back to non-E2EE if the room is confirmed unencrypted.
- **Room identifiers**: Scripts accept short name (`agent-work`), room alias (`#room:server`), room ID (`!abc:server`), or a `https://matrix.to/#/…` link. A short name (also `#name` without server) is looked up as in version 4, alias before display name, two or three requests per joined room; several matches stop the command. A room without a name (a direct chat) goes by the name Element shows: the other person's display name or user ID. Use `matrix-rooms.py` to discover.
- **Config**: `~/.config/matrix/config.json` — required: `homeserver`, `user_id`; optional: `access_token` (non-E2EE only; or `access_token_file`, or `MATRIX_ACCESS_TOKEN`), `bot_prefix`, `watch_rooms` (rooms the daemon logs).
- **Running scripts**: `uv run` for every script, `matrix-doctor.py` included; it picks Python 3.11 or later from the PEP 723 block.
- **Bash `!` handling**: Prepend `set +H &&` before any command whose arguments contain `!` — history expansion corrupts otherwise.
- **Secure defaults** (opt-ins in [SKILL.md](skills/matrix-communication/SKILL.md)): secrets come from `MATRIX_PASSWORD` / `MATRIX_RECOVERY_KEY` / `MATRIX_RECOVERY_PASSPHRASE` or a prompt, never argv (`--allow-secret-argument`); room keys go to verified devices only (`--trust-unverified-devices`, one message, nothing stored).
- **Key backup**: `--import-keys` restores; without it (or `--status`) the script refuses.
- **Device verification**: Use Element Desktop or Element Android — Element X has incompatible verification flows.
- **Output** of the E2EE scripts is matrix-e2ee-cli's own stdout and stderr, passed through (a failed `--json` send, edit, react or redact also prints the old `{"error": …}` object on stdout); a one-time takeover of a matrix-nio device reports on stderr only, so callers parsing stdout see the command's output alone.
- **Dependencies**: `uv` (runs the scripts on Python 3.11 or later), Matrix homeserver access. E2EE downloads the matrix-e2ee-cli release binary on first use (Linux and macOS x86_64/arm64, Windows x86_64); the first E2EE run takes a few seconds for the initial key sync.

## Testing

Use the `#test` room (or a room named `test`) for all testing. Never test in production rooms. Send a message and verify it appears in Element to confirm E2EE works end-to-end.

## References

### matrix-communication
- [SKILL.md](skills/matrix-communication/SKILL.md) — skill definition and quick reference
- [Command Reference](skills/matrix-communication/references/command-reference.md) — every script and flag, script selection, config · [Troubleshooting](skills/matrix-communication/references/troubleshooting.md) · [Agent governance](skills/matrix-communication/references/agent-governance.md)
- [Setup Guide](skills/matrix-communication/references/setup-guide.md) · [E2EE Guide](skills/matrix-communication/references/e2ee-guide.md) · [Messaging Guide](skills/matrix-communication/references/messaging-guide.md) · [API Reference](skills/matrix-communication/references/api-reference.md)

### matrix-administration
- [SKILL.md](skills/matrix-administration/SKILL.md) — skill definition and quick reference
- [Synapse Admin API endpoints](skills/matrix-administration/references/synapse-admin-api.md)
- [Room health checks](skills/matrix-administration/references/room-health-checks.md)
- [Room graph pipeline](skills/matrix-administration/references/room-graph-pipeline.md)
- [Safety guide](skills/matrix-administration/references/safety-guide.md)

### matrix-announcement
- [SKILL.md](skills/matrix-announcement/SKILL.md) — five rules + type-tag list + pre-send checklist
- [HTML subset](skills/matrix-announcement/references/html-subset.md)
- [Structure & length budget](skills/matrix-announcement/references/structure.md)
- [Glyphs](skills/matrix-announcement/references/glyphs.md)
- [Image cards (HTML→PNG)](skills/matrix-announcement/references/image-cards.md)
- [Threading, mentions, edits, redactions](skills/matrix-announcement/references/threading.md)
- [Anti-patterns](skills/matrix-announcement/references/anti-patterns.md)
- [Text templates](skills/matrix-announcement/references/text-templates.md)
- [Visual gallery](skills/matrix-announcement/references/gallery.html)

### Repo
- [Architecture](docs/ARCHITECTURE.md) — system design and distribution · [Security assurance case](docs/SECURITY-ASSURANCE.md) — trust boundaries, where tokens and key material are read, stored and sent, limits
- [Source](https://github.com/netresearch/matrix-skill)
