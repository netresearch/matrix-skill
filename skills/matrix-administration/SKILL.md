---
name: matrix-administration
description: "Use when administering a Synapse Matrix homeserver — snapshot rooms, rate room health, render a Graphviz map, force-join users, promote admins, harden rooms (add-to-space + restrict + encrypt), deactivate users, search unencrypted history, find biggest rooms by DB size. Requires a Synapse server-admin access token."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python3 (stdlib only). Optional: graphviz `dot` for SVG rendering. Synapse 1.x homeserver with admin API enabled."
metadata:
  author: Netresearch DTT GmbH
  version: "1.0.0"
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

These scripts hold an admin token. See [`references/safety-guide.md`](references/safety-guide.md).

- **`synapse-deactivate-user.py`** is irreversible.
- **`synapse-migrate-room.py`** enables encryption (cannot be undone) and switches public rooms to `restricted` (users outside the parent space lose discoverability).
- **`synapse-search.py`** cannot read E2EE messages — empty results ≠ no messages.
- `rooms.json` exposes user IDs; never commit it.

## References

- [`references/synapse-admin-api.md`](references/synapse-admin-api.md), [`references/room-health-checks.md`](references/room-health-checks.md), [`references/room-graph-pipeline.md`](references/room-graph-pipeline.md), [`references/safety-guide.md`](references/safety-guide.md)
- Source: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
