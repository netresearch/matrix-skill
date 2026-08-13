# Matrix Skill

Agentic Skills for Matrix, distributed as a Claude Code plugin. Three skills ship in this repo:

| Skill | Purpose | API surface |
|-------|---------|-------------|
| [**matrix-communication**](skills/matrix-communication/) | Send / read / edit / react in chat rooms on behalf of a regular user, with full E2EE support, and follow a room live through a daemon | Matrix Client-Server API |
| [**matrix-administration**](skills/matrix-administration/) | Operate a Synapse homeserver — snapshot rooms, rate room health, render a Graphviz map, force-join, promote, harden, deactivate, search history | Synapse Admin API |
| [**matrix-announcement**](skills/matrix-announcement/) | Compose scannable, structured Matrix announcements — release notes, digests, heads-ups, postmortems. HTML subset, type-tag system, glyph rules, and HTML-card-to-PNG templates. | Content guidance only — pairs with `matrix-communication` |

The three skills are independent — you can install the plugin and use any combination. `matrix-communication` and `matrix-administration` share `~/.config/matrix/config.json`. `matrix-announcement` has no runtime; it's reference material the agent reads while composing messages.

**What is an Agentic Skill?** Platform-agnostic instructions and tools that AI coding agents can use. This skill is packaged as a Claude Code plugin but follows the open [Agentic Skills specification](https://github.com/anthropics/agentic-skills).

## matrix-communication — Features

**Follow a room while you work.** `matrix-watchd.py` holds the E2EE store, syncs,
decrypts, and appends every event of a watched room to a per-room JSONL log.
`matrix-watch.py` follows that log without opening the store, so any number of
readers run at once — an agent can stay current with a room, post its status and
answer, without a second process ever touching the encryption state.

- **Send messages** to any joined Matrix room
- **Rich formatting** — bold, italic, code, strikethrough, spoilers, lists, blockquotes
- **Real mentions** — `--mention '@user:server'` sets `m.mentions`, which is what
  notifies a client, and renders that name in your text as a pill; a plain
  `@name` without `--mention` does neither
- **Smart link shortening** — Jira, GitHub, GitLab URLs become readable links
- **Room links** — `#room:server` becomes a clickable room link
- **Code blocks** — syntax-highlighted multi-line code
- **Emotes** — `/me` style action messages (`--emote`)
- **Thread replies** — keep discussions organized (`--thread`)
- **Reactions** — add emoji reactions to messages
- **Edit and redact** — modify or delete messages you sent
- **Visual effects** — confetti, fireworks, snowfall (Element clients)
- **List rooms** to find the right destination
- **Read messages** — both unencrypted and E2EE decryption
- **Bot prefix** — optional 🤖 prefix for automated messages
- **Device verification** — SAS emoji verification for E2EE
- **One writer per store** — every path that opens the E2EE store takes an
  exclusive lock, so two processes cannot corrupt it

## Installation

### Marketplace (Recommended)

Add the [Netresearch marketplace](https://github.com/netresearch/claude-code-marketplace) once, then browse and install skills:

```bash
# Claude Code
/plugin marketplace add netresearch/claude-code-marketplace
```

### npx ([skills.sh](https://skills.sh))

Install with any [Agent Skills](https://agentskills.io)-compatible agent:

```bash
npx skills add https://github.com/netresearch/matrix-skill --skill matrix-communication
```

### Download Release

Download the [latest release](https://github.com/netresearch/matrix-skill/releases/latest) and extract to your agent's skills directory.

### Git Clone

```bash
git clone https://github.com/netresearch/matrix-skill.git
```

### Composer (PHP Projects)

```bash
composer require netresearch/matrix-skill
```

Requires [netresearch/composer-agent-skill-plugin](https://github.com/netresearch/composer-agent-skill-plugin).
### npm (Node Projects)

```bash
npm install --save-dev \
  @netresearch/agent-skill-coordinator \
  github:netresearch/matrix-skill
```

Requires [@netresearch/agent-skill-coordinator](https://github.com/netresearch/node-agent-skill-coordinator), which discovers the skill in `node_modules` and registers it in `AGENTS.md` via a `postinstall` hook. For pnpm, also allowlist the coordinator's postinstall:

```json
{
  "pnpm": {
    "onlyBuiltDependencies": ["@netresearch/agent-skill-coordinator"]
  }
}
```

## Prerequisites

**For E2EE support** (most Matrix rooms), install libolm:

```bash
sudo apt install libolm-dev    # Debian/Ubuntu
sudo dnf install libolm-devel  # Fedora
brew install libolm            # macOS
```

## Usage

Paths are shortened to `$C` below:

```bash
C=skills/matrix-communication/scripts
```

The `*-e2ee.py` scripts are the ones to use. Most Matrix rooms are encrypted, and
the non-E2EE variants cannot read or write in them. Prepend `set +H` to any
command whose arguments contain `!`, or bash history expansion eats it.

### Send a Message

```bash
set +H && uv run $C/matrix-send-e2ee.py "#myroom:matrix.org" "Deployment complete"
set +H && uv run $C/matrix-send-e2ee.py "!abc123:matrix.org" "**Build passed** for abc123"

# Notify someone. --mention is what actually reaches them.
set +H && uv run $C/matrix-send-e2ee.py "#dev:matrix.org" \
  "alex, schaust du drauf?" --mention '@alex:matrix.org'
```

### Follow a Room

```bash
# Add rooms to watch_rooms in ~/.config/matrix/config.json, then:
uv run $C/matrix-watchd.py --start
uv run $C/matrix-watchd.py --status

# One line per event on stdout, for a human or an agent's monitor
uv run $C/matrix-watch.py "#myroom:matrix.org"

# What arrived since this reader last looked, then exit
uv run $C/matrix-watch.py "#myroom:matrix.org" --once
```

While the daemon runs it owns the store; send, react, redact and edit route
through it automatically. With no daemon they open the store themselves. Nothing
changes at the call site either way.

### List Joined Rooms

```bash
uv run $C/matrix-rooms.py
uv run $C/matrix-rooms.py --search ops
```

### Read Messages

```bash
uv run $C/matrix-read-e2ee.py "#myroom:matrix.org" --limit 10
uv run $C/matrix-read-e2ee.py "#myroom:matrix.org" --limit 50 --json
```

### Resolve Room Alias

```bash
uv run $C/matrix-resolve.py "#myroom:matrix.org"
```

### Check the Setup

```bash
python3 $C/matrix-doctor.py          # verifies every credential against the homeserver
```

## E2EE Support

`matrix-e2ee-setup.py` creates a dedicated "Matrix Skill E2EE" device that runs
alongside your Element client. It logs in once with your password, which is used
and not stored.

| Script | Purpose |
|--------|---------|
| `matrix-send-e2ee.py` | Send encrypted messages |
| `matrix-read-e2ee.py` | Read and decrypt messages |
| `matrix-edit-e2ee.py` | Edit a message you sent |
| `matrix-download-e2ee.py` | Download and decrypt attachments |
| `matrix-e2ee-setup.py` | Create or remove the agent's device |
| `matrix-e2ee-verify.py` | SAS emoji verification |
| `matrix-fetch-keys.py` | Request missing room keys from your other devices |
| `matrix-key-backup.py` | Restore room keys from the server-side backup |
| `matrix-watchd.py` | The daemon that owns the store and follows rooms |

First run takes ~2–5 s for the initial key sync; later runs are faster.

### Never reuse a running client's access token

Not from Element, Element X, FluffyChat or a browser session. A token carries a
`device_id`, and E2EE state is per device: two clients on one device cannot read
each other's messages, and the one that breaks is the client you use — it starts
showing `[Unable to decrypt]` for its own messages. Nothing fails at the moment
you paste it.

Earlier versions of this documentation offered that as a fallback "if
password-based setup isn't possible". That advice was wrong and is retracted. No
password means no E2EE, and that is the answer.

### Verification

```bash
C=skills/matrix-communication/scripts

# You start it, aimed at one of your own devices
uv run $C/matrix-e2ee-verify.py --list                      # find the device id
uv run $C/matrix-e2ee-verify.py --request DEVICE --timeout 300

# Or Element starts it and this side waits — needs --listen
uv run $C/matrix-e2ee-verify.py --listen --timeout 300
```

Without `--request` **and** without `--listen` the script picks a device itself,
which is rarely the one you are sitting in front of.

Use Element Desktop or Element Android. Element X has an incompatible
verification flow.

### The matrix-nio pin

The scripts pin `matrix-nio[e2e]<0.26`. 0.26 sends the SAS commitment in a
format Element rejects, so no verification completes
([matrix-nio#570](https://github.com/matrix-nio/matrix-nio/issues/570)), and the
two releases write incompatible store formats — opening one with the other fails
as `BAD_ACCOUNT_KEY`, which names a key that is not the problem.

Moving the pin is a migration, not a version bump. The store cannot be
converted:

```bash
uv run $C/matrix-e2ee-setup.py --logout && uv run $C/matrix-e2ee-setup.py
uv run $C/matrix-key-backup.py --import-keys
uv run $C/matrix-e2ee-verify.py --request DEVICE
```

## matrix-administration — Features

Synapse homeserver administration via the [Synapse Admin API](https://element-hq.github.io/synapse/latest/usage/administration/admin_api/index.html). **Stdlib-only Python** (no E2EE deps required). Works against any Synapse 1.x server.

- Paginated room snapshot (`synapse-fetch-rooms.py` → `rooms.json`)
- Health rating with EN+DE phrasing — public, unencrypted, orphaned-from-spaces
- Colour-coded Graphviz SVG of the entire room/space tree
- Force-join, promote-admin, link-room-to-space
- One-shot hardening pipeline: add to space + restrict joins + enable encryption + restore power levels
- **Destructive** user deactivation with optional GDPR `--erase`
- Inspection: list user's admin/membership rooms, replay join/leave timelines, search unencrypted history, find biggest rooms by DB size

Quick start:

```bash
# Snapshot all rooms (the admin token comes from ~/.config/matrix/config.json)
python3 skills/matrix-administration/scripts/synapse-fetch-rooms.py

# Rate them in German, treating !home:example.com as our home space
python3 skills/matrix-administration/scripts/synapse-rate-rooms.py \
    --language de --space '!home:example.com'

# Render a Graphviz SVG (requires the `dot` binary)
python3 skills/matrix-administration/scripts/synapse-graph.py --space '!home:example.com'
```

Full reference and safety guide live in [`skills/matrix-administration/`](skills/matrix-administration/).

## matrix-announcement — Features

Content-design guidance for any agent-authored Matrix room post longer than a single line — release notes, version bumps, weekly digests, breaking-change heads-ups, postmortems, RFCs, multi-skill pipeline summaries.

- **Five rules** — one headline, `formatted_body` always, lists beat paragraphs, code in `<pre><code>`, layout-heavy → render to PNG
- **Type-tag system** — `Release` / `Patch` / `Heads-up` / `Digest` / `Postmortem` / `RFC` / `New skill`. Pick one; never stack.
- **Glyph rules** — one prefix glyph max, no rockets (🚀), no party emoji (🎉), no multi-emoji ladders
- **`m.text` vs `m.notice`** — `m.notice` for unattended automation (bots can't auto-reply, prevents loops)
- **Three rendered HTML card templates** — `release-card.html` (1200×630), `weekly-digest.html` (1200×1500), `comparison.html` (1200×900) — render headlessly with Chromium and post as `m.image`
- **Seven `formatted_body` skeletons** — drop-in templates for each type tag
- **Visual gallery** at `skills/matrix-announcement/references/gallery.html` — preview every rule, all five worked examples, and the three card templates side-by-side

```bash
# Open the live preview gallery
xdg-open skills/matrix-announcement/references/gallery.html

# Render a release card to PNG
chromium --headless=new --hide-scrollbars --window-size=1200,630 \
  --screenshot=card.png \
  "file://$(pwd)/skills/matrix-announcement/references/templates/release-card.html"
```

Full reference lives in [`skills/matrix-announcement/`](skills/matrix-announcement/).

## Structure

```
matrix-skill/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest (lists all three skills)
├── skills/
│   ├── matrix-communication/    # Client-Server API, E2EE chat
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── _lib/                    # stdlib-only shared helpers
│   │   │   ├── matrix-create-room.py    # Create a room
│   │   │   ├── matrix-doctor.py         # Health check (python3, not uv run)
│   │   │   ├── matrix-download-e2ee.py  # Download attachments (E2EE)
│   │   │   ├── matrix-e2ee-setup.py     # Create or remove the agent device
│   │   │   ├── matrix-e2ee-verify.py    # SAS emoji verification
│   │   │   ├── matrix-edit-e2ee.py      # Edit (E2EE) — USE THIS
│   │   │   ├── matrix-edit.py           # Edit (non-E2EE fallback)
│   │   │   ├── matrix-fetch-keys.py     # Request missing room keys
│   │   │   ├── matrix-invite.py         # Invite a user
│   │   │   ├── matrix-key-backup.py     # Restore keys from server backup
│   │   │   ├── matrix-power-level.py    # Read or set power levels
│   │   │   ├── matrix-react.py          # React to messages
│   │   │   ├── matrix-read-e2ee.py      # Read (E2EE) — USE THIS
│   │   │   ├── matrix-read.py           # Read (non-E2EE fallback)
│   │   │   ├── matrix-redact.py         # Delete messages
│   │   │   ├── matrix-resolve.py        # Resolve aliases
│   │   │   ├── matrix-rooms.py          # List rooms
│   │   │   ├── matrix-send-e2ee.py      # Send (E2EE) — USE THIS
│   │   │   ├── matrix-send.py           # Send (non-E2EE fallback)
│   │   │   ├── matrix-watch.py          # Follow a room's event log
│   │   │   └── matrix-watchd.py         # Daemon: owns the store, follows rooms
│   │   └── references/
│   ├── matrix-administration/  # Synapse Admin API, server ops
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── _lib/                    # stdlib-only shared helpers
│   │   │   ├── synapse-fetch-rooms.py
│   │   │   ├── synapse-rate-rooms.py
│   │   │   ├── synapse-graph.py
│   │   │   ├── synapse-biggest-rooms.py
│   │   │   ├── synapse-join-room.py
│   │   │   ├── synapse-make-admin.py
│   │   │   ├── synapse-add-to-space.py
│   │   │   ├── synapse-migrate-room.py
│   │   │   ├── synapse-deactivate-user.py
│   │   │   ├── synapse-user-admin-rooms.py
│   │   │   ├── synapse-user-rooms.py
│   │   │   ├── synapse-room-member-flow.py
│   │   │   └── synapse-search.py
│   │   └── references/
│   │       ├── synapse-admin-api.md
│   │       ├── room-health-checks.md
│   │       ├── room-graph-pipeline.md
│   │       └── safety-guide.md
│   └── matrix-announcement/    # Content guidance (no scripts)
│       ├── SKILL.md
│       ├── README.md
│       ├── evals/evals.json
│       └── references/
│           ├── html-subset.md
│           ├── structure.md
│           ├── glyphs.md
│           ├── image-cards.md
│           ├── threading.md
│           ├── anti-patterns.md
│           ├── text-templates.md
│           ├── gallery.html              # visual preview of all rules + examples
│           └── templates/
│               ├── release-card.html     # 1200×630
│               ├── weekly-digest.html    # 1200×1500
│               └── comparison.html       # 1200×900
├── docs/
│   ├── ARCHITECTURE.md          # system design and distribution
│   ├── specs/                   # design documents (OKF)
│   └── exec-plans/              # implementation plans
├── LICENSE-MIT           # Code license (MIT)
├── LICENSE-CC-BY-SA-4.0  # Content license (CC-BY-SA-4.0)
└── README.md
```

## License

This project uses split licensing:

- **Code** (scripts, workflows, configs): [MIT](LICENSE-MIT)
- **Content** (skill definitions, documentation, references): [CC-BY-SA-4.0](LICENSE-CC-BY-SA-4.0)

See the individual license files for full terms.
## Author

Netresearch DTT GmbH - https://www.netresearch.de
