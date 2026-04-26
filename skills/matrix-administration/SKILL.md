---
name: matrix-administration
description: "Use this skill for ANY Synapse / Matrix homeserver administration task — listing or snapshotting all rooms on a server, rating room health (public, unencrypted, orphaned-from-spaces), rendering a Graphviz map of the room/space tree, force-joining users, promoting users to room admin, hardening rooms (add-to-space + restrict joins + enable encryption), deactivating Matrix users (also for GDPR erasure), finding biggest rooms by DB size, listing where a user is a room admin or member, replaying join/leave timelines, or searching unencrypted history. ALWAYS trigger when the user mentions Synapse Admin API, '/_synapse/admin', server-wide room operations, Matrix user offboarding, or anything that needs a homeserver-admin access token — even when they don't explicitly say 'admin API'. Companion to matrix-communication (which handles regular chat as a user)."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python3 (stdlib only) and a Matrix access token belonging to a Synapse server-admin user. Optional: graphviz `dot` binary for SVG rendering. Synapse 1.x homeserver with admin API enabled."
metadata:
  author: Netresearch DTT GmbH
  version: "1.20.1"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(python3:*) Bash(uv:*) Bash(dot:*) Read Write
---

# Matrix Administration

Administer a Synapse homeserver via the [Admin API](https://element-hq.github.io/synapse/latest/usage/administration/admin_api/index.html). Stdlib-only Python; reads `~/.config/matrix/config.json`. Companion to **matrix-communication**.

## Quick Reference

```bash
S=skills/matrix-administration/scripts

# Snapshot every room → rooms.json
python3 $S/synapse-fetch-rooms.py [--server :example.com]

# Local analysis of rooms.json
python3 $S/synapse-rate-rooms.py    --space '!home:server' [--language de]
python3 $S/synapse-graph.py         --space '!home:server'
python3 $S/synapse-user-rooms.py    '@user:server'
python3 $S/synapse-user-admin-rooms.py '@user:server'

# Live admin API
python3 $S/synapse-biggest-rooms.py     [-n 10]
python3 $S/synapse-join-room.py         '!room:server' '@user:server'
python3 $S/synapse-make-admin.py        '!room:server' '@user:server'
python3 $S/synapse-deactivate-user.py   '@user:server'   # DESTRUCTIVE

# Live client API
python3 $S/synapse-add-to-space.py      '!room:server' '!space:server'
python3 $S/synapse-migrate-room.py      '!room:server' '@admin:server' '!space:server'
python3 $S/synapse-room-member-flow.py  '!room:server'
python3 $S/synapse-search.py            '!room:server' '@bot:server' deploy
```

## Scripts

| Script | Purpose |
|--------|---------|
| `synapse-fetch-rooms.py` | Snapshot all rooms + state into `rooms.json` |
| `synapse-rate-rooms.py` | Health checks (public / unencrypted / orphaned), EN+DE |
| `synapse-graph.py` | Render `rooms.json` → Graphviz `.dot` + `.svg` |
| `synapse-biggest-rooms.py` | Top-N rooms by Synapse-estimated DB size |
| `synapse-join-room.py` | Force-join a user |
| `synapse-make-admin.py` | Promote to power-level 100 |
| `synapse-add-to-space.py` | Send `m.space.child` linking room → space |
| `synapse-migrate-room.py` | Add to space + restrict joins + enable encryption |
| `synapse-deactivate-user.py` | **Destructive** user deactivation (`--erase` for GDPR) |
| `synapse-user-admin-rooms.py` | Where is user PL 100, with co-admin count |
| `synapse-user-rooms.py` | All rooms a user is a member of |
| `synapse-room-member-flow.py` | Chronological join/leave timeline |
| `synapse-search.py` | Unencrypted history search (E2EE rooms return nothing) |

## Setup

`~/.config/matrix/config.json`:

```json
{
  "homeserver": "https://matrix.example.com",
  "admin_token": "syt_admin_…",
  "room_filter": ":example.com",
  "default_space_id": "!home:example.com",
  "home_space_ids": ["!home:example.com"]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `homeserver` | yes | Server base URL |
| `admin_token` | yes (or `access_token`) | Server-admin token |
| `room_filter` | no | Suffix filter for fetch + member-flow |
| `default_space_id` | no | Fallback space for migrate / add-to-space |
| `home_space_ids` | no | Spaces treated as "home" by the rater |

Env fallbacks: `MATRIX_USER_ID`, `MATRIX_SPACE_ID`, `LANGUAGE=en|de`, `NO_COLOR`.

## Safety

These scripts hold an admin token. Read [`references/safety-guide.md`](references/safety-guide.md) before any destructive operation.

- **`synapse-deactivate-user.py`** is irreversible without a database operation.
- **`synapse-migrate-room.py`** enables encryption (cannot be undone) and switches public rooms to `restricted` (users outside the parent space lose discoverability). Power-level changes are restored on exit, including on Ctrl-C.
- **`synapse-make-admin.py`** raises a user to power-level 100 permanently — call it deliberately, not as a workaround for a missing invite.
- **`synapse-search.py`** cannot read end-to-end-encrypted messages. Empty results ≠ no messages — say so when you report findings.
- `rooms.json` exposes user IDs and power levels for every indexed room; never commit it.

## References

- [`references/synapse-admin-api.md`](references/synapse-admin-api.md) — every endpoint used and where to find upstream docs
- [`references/room-health-checks.md`](references/room-health-checks.md) — rating rules and remediation
- [`references/room-graph-pipeline.md`](references/room-graph-pipeline.md) — periodic SVG dashboard recipe (Docker)
- [`references/safety-guide.md`](references/safety-guide.md) — pre-flight checklist for destructive operations
- Source: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
