# Matrix Administration

Operate on a Synapse Matrix homeserver via the [Synapse Admin API](https://element-hq.github.io/synapse/latest/usage/administration/admin_api/index.html). Companion to the **matrix-communication** skill in this repo.

## Features

- **Snapshot every room** — `rooms.json` of every visible room and its state
- **Health rating** — flag public, unencrypted, or orphaned-from-spaces rooms (English + German)
- **Graphviz map** — colour-coded SVG of the homeserver's room/space tree
- **Force-join, promote admin, link to space** — point-and-shoot moderation tools
- **Hardening pipeline** — `synapse-migrate-room.py` adds a room to a space, restricts joins, enables encryption, and restores power levels
- **Deactivate users** — destructive, with optional GDPR `--erase`
- **Inspection** — list a user's admin/membership rooms, replay join/leave timelines, search unencrypted history
- **Stdlib-only Python** — no third-party dependencies

## Installation

### Via the Netresearch marketplace (recommended)

```bash
/plugin marketplace add netresearch/claude-code-marketplace
```

Then `/install-plugin netresearch/matrix-skill`. Both `matrix-communication` and `matrix-administration` ship in the same plugin.

### Via release download

Grab the [latest release](https://github.com/netresearch/matrix-skill/releases/latest) and extract to `~/.claude/skills/matrix-administration/`.

## Configuration

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

The token must belong to a user with **server-admin** rights (`user_type: 'admin'` on the user object). `room_filter`, `default_space_id`, and `home_space_ids` are optional — none of them ship pre-set.

## Usage

The skill triggers on Synapse-admin tasks: "list all rooms on the homeserver", "rate room health", "deactivate user `@bob`", "find rooms with no admin in our org space".

### Example prompts

```
"Snapshot every room on matrix.example.com and rate them in German"
"Render an SVG of the room tree, treating !home:example.com as our home space"
"Deactivate @leaver:example.com and erase their messages"
"Where is @alice:example.com a room admin? Highlight rooms with no other admins."
"Make !room:example.com private, add it to !home:example.com, and enable encryption"
```

## Structure

```
matrix-administration/
├── SKILL.md                            # AI instructions
├── README.md                           # this file
├── scripts/
│   ├── _lib/                           # stdlib-only shared helpers
│   ├── synapse-fetch-rooms.py
│   ├── synapse-rate-rooms.py
│   ├── synapse-graph.py
│   ├── synapse-biggest-rooms.py
│   ├── synapse-join-room.py
│   ├── synapse-make-admin.py
│   ├── synapse-add-to-space.py
│   ├── synapse-migrate-room.py
│   ├── synapse-deactivate-user.py
│   ├── synapse-user-admin-rooms.py
│   ├── synapse-user-rooms.py
│   ├── synapse-room-member-flow.py
│   └── synapse-search.py
└── references/
    ├── synapse-admin-api.md            # endpoints used + upstream docs
    ├── room-health-checks.md           # rule definitions
    ├── room-graph-pipeline.md          # periodic SVG dashboard with Docker
    └── safety-guide.md                 # destructive-operation checklist
```

## Safety

These scripts hold an admin token. **Read [`references/safety-guide.md`](references/safety-guide.md) before running anything new.** Highlights:

- `synapse-deactivate-user.py` is irreversible.
- `synapse-migrate-room.py` enables encryption — irreversible — and removes discoverability for users outside the parent space.
- `rooms.json` exposes user IDs / power levels for every room. Never commit it.

## License

MIT for code, CC-BY-SA-4.0 for documentation. See [`LICENSE-MIT`](../../LICENSE-MIT) and [`LICENSE-CC-BY-SA-4.0`](../../LICENSE-CC-BY-SA-4.0).

## Credits

Developed and maintained by [Netresearch DTT GmbH](https://www.netresearch.de/). Originally derived from the internal `matrix-tools` Node.js scripts; ported to Python and generalised for any Synapse homeserver.

---

**Made with ❤️ for Open Source by [Netresearch](https://www.netresearch.de/)**
