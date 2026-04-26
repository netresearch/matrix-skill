---
name: matrix-administration
description: "Use when administering a Synapse / Matrix homeserver — list or snapshot all rooms, rate room health (public, unencrypted, orphaned), render a Graphviz map of the room/space tree, force-join users, promote room admins, harden rooms (add-to-space + restrict + encrypt), deactivate Matrix users (with GDPR erase), find biggest rooms by DB size, audit where a user is admin or member, replay join/leave timelines, or search unencrypted history. Trigger on any '/_synapse/admin', server-wide room operation, Matrix user offboarding, or anything requiring a homeserver-admin token — even without 'admin API' in the prompt. Companion to matrix-communication."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "python3 (stdlib only) + a Matrix access token belonging to a Synapse server-admin user. Optional: graphviz `dot` for SVG. Synapse 1.x with admin API enabled."
metadata:
  author: Netresearch DTT GmbH
  version: "1.20.1"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(python3:*) Bash(uv:*) Bash(dot:*) Read Write
---

# Matrix Administration

Stdlib-only Python wrappers around the Synapse [Admin API](https://element-hq.github.io/synapse/latest/usage/administration/admin_api/index.html) and the Client-Server API. Reads `~/.config/matrix/config.json` (the same file matrix-communication uses).

## Quick Reference

```bash
S=skills/matrix-administration/scripts

python3 $S/synapse-fetch-rooms.py [--server :example.com]
python3 $S/synapse-rate-rooms.py --space '!home:srv' [--language de]
python3 $S/synapse-graph.py --space '!home:srv'
python3 $S/synapse-biggest-rooms.py [-n 10]

python3 $S/synapse-join-room.py    '!room:srv' '@user:srv'
python3 $S/synapse-make-admin.py   '!room:srv' '@user:srv'
python3 $S/synapse-add-to-space.py '!room:srv' '!space:srv'
python3 $S/synapse-migrate-room.py '!room:srv' '@admin:srv' '!space:srv'

python3 $S/synapse-deactivate-user.py   '@user:srv'   # DESTRUCTIVE
python3 $S/synapse-user-rooms.py        '@user:srv'
python3 $S/synapse-user-admin-rooms.py  '@user:srv'
python3 $S/synapse-room-member-flow.py  '!room:srv'
python3 $S/synapse-search.py            '!room:srv' '@bot:srv' deploy
```

## Scripts

| Script | Purpose |
|--------|---------|
| `synapse-fetch-rooms.py` | Snapshot all rooms + state → `rooms.json` |
| `synapse-rate-rooms.py` | Health checks (EN/DE) on `rooms.json` |
| `synapse-graph.py` | Render `rooms.json` → Graphviz `.dot` + `.svg` |
| `synapse-biggest-rooms.py` | Top-N rooms by DB size |
| `synapse-join-room.py` | Force-join a user |
| `synapse-make-admin.py` | Promote to PL 100 |
| `synapse-add-to-space.py` | Send `m.space.child` |
| `synapse-migrate-room.py` | Add to space + restrict + encrypt |
| `synapse-deactivate-user.py` | **Destructive** deactivation (`--erase` for GDPR) |
| `synapse-user-admin-rooms.py` | Local: rooms where user is PL 100 |
| `synapse-user-rooms.py` | Local: rooms a user belongs to |
| `synapse-room-member-flow.py` | Join/leave timeline |
| `synapse-search.py` | Unencrypted history search |

## Setup

`~/.config/matrix/config.json` (respects `$XDG_CONFIG_HOME`):

```json
{
  "homeserver": "https://matrix.example.com",
  "admin_token": "syt_admin_…",
  "room_filter": ":example.com",
  "default_space_id": "!home:example.com",
  "home_space_ids": ["!home:example.com"]
}
```

`homeserver` and either `admin_token` or `access_token` (server-admin) are required. The other fields are optional. Env fallbacks: `MATRIX_USER_ID`, `MATRIX_SPACE_ID`, `LANGUAGE=en|de`, `NO_COLOR`.

## Safety

The token is server-admin. Read [`references/safety-guide.md`](references/safety-guide.md) before any destructive op.

- `synapse-deactivate-user.py` is irreversible.
- `synapse-migrate-room.py` enables encryption (one-way) and restricts joins; power-level changes restored on exit including Ctrl-C.
- `synapse-make-admin.py` raises PL 100 permanently.
- `synapse-search.py` cannot read E2EE — empty ≠ no messages.
- `rooms.json` exposes user IDs; never commit it.

## References

- [`references/synapse-admin-api.md`](references/synapse-admin-api.md) — endpoints + upstream docs
- [`references/room-health-checks.md`](references/room-health-checks.md) — rules + remediation
- [`references/room-graph-pipeline.md`](references/room-graph-pipeline.md) — Docker dashboard recipe
- [`references/safety-guide.md`](references/safety-guide.md) — destructive-op checklist
- Source: [netresearch/matrix-skill](https://github.com/netresearch/matrix-skill)
