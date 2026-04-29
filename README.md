# Matrix Skill

Agentic Skills for Matrix, distributed as a Claude Code plugin. Three skills ship in this repo:

| Skill | Purpose | API surface |
|-------|---------|-------------|
| [**matrix-communication**](skills/matrix-communication/) | Send / read / edit / react in chat rooms on behalf of a regular user, with full E2EE support | Matrix Client-Server API |
| [**matrix-administration**](skills/matrix-administration/) | Operate a Synapse homeserver — snapshot rooms, rate room health, render a Graphviz map, force-join, promote, harden, deactivate, search history | Synapse Admin API |
| [**matrix-announcement**](skills/matrix-announcement/) | Compose scannable, structured Matrix announcements — release notes, digests, heads-ups, postmortems. HTML subset, type-tag system, glyph rules, and HTML-card-to-PNG templates. | Content guidance only — pairs with `matrix-communication` |

The three skills are independent — you can install the plugin and use any combination. `matrix-communication` and `matrix-administration` share `~/.config/matrix/config.json`. `matrix-announcement` has no runtime; it's reference material the agent reads while composing messages.

**What is an Agentic Skill?** Platform-agnostic instructions and tools that AI coding agents can use. This skill is packaged as a Claude Code plugin but follows the open [Agentic Skills specification](https://github.com/anthropics/agentic-skills).

## matrix-communication — Features

- **Send messages** to any joined Matrix room
- **Rich formatting** - bold, italic, code, strikethrough, spoilers, lists, blockquotes
- **Smart link shortening** - Jira, GitHub, GitLab URLs become readable links
- **Matrix mentions** - `@user:server` becomes clickable user pill
- **Room links** - `#room:server` becomes clickable room link
- **Code blocks** - Syntax-highlighted multi-line code
- **Emotes** - `/me` style action messages (`--emote`)
- **Thread replies** - Keep discussions organized (`--thread`)
- **Reactions** - Add emoji reactions to messages (✅ 👍 🚀)
- **Edit messages** - Modify sent messages
- **Redact messages** - Delete messages from rooms
- **Visual effects** - Confetti 🎉, fireworks 🎆, snowfall ❄️ (Element clients)
- **List rooms** to find the right destination
- **Read messages** - both unencrypted and E2EE decryption
- **Bot prefix** - optional 🤖 prefix for automated messages
- **Device verification** - SAS emoji verification for E2EE

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
## Prerequisites

**For E2EE support** (most Matrix rooms), install libolm:

```bash
sudo apt install libolm-dev    # Debian/Ubuntu
sudo dnf install libolm-devel  # Fedora
brew install libolm            # macOS
```

## Usage

### Send a Message

```bash
# By room alias
uv run skills/matrix-communication/scripts/matrix-send.py "#myroom:matrix.org" "Deployment complete!"

# By room ID
uv run skills/matrix-communication/scripts/matrix-send.py "!abc123:matrix.org" "Hello!"

# With markdown formatting
uv run skills/matrix-communication/scripts/matrix-send.py "#dev:matrix.org" "**Build passed** for commit abc123"
```

### List Joined Rooms

```bash
# List all rooms
uv run skills/matrix-communication/scripts/matrix-rooms.py

# Search for specific room
uv run skills/matrix-communication/scripts/matrix-rooms.py --search ops
```

### Read Messages

```bash
# Read last 10 messages (unencrypted rooms)
uv run skills/matrix-communication/scripts/matrix-read.py "#myroom:matrix.org"

# Read E2EE encrypted messages
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py "#myroom:matrix.org" --limit 10

# Read more messages
uv run skills/matrix-communication/scripts/matrix-read.py "#myroom:matrix.org" --limit 50
```

### Resolve Room Alias

```bash
uv run skills/matrix-communication/scripts/matrix-resolve.py "#myroom:matrix.org"
```

## E2EE Support

E2EE is set up automatically when you configure the skill via the agent. The agent creates a dedicated "Matrix Skill E2EE" device that works alongside your Element client without conflicts.

| Script | Purpose |
|--------|---------|
| `matrix-send-e2ee.py` | Send encrypted messages |
| `matrix-read-e2ee.py` | Read/decrypt messages |
| `matrix-edit-e2ee.py` | Edit messages (encrypted) |
| `matrix-e2ee-verify.py` | Device verification |

*First run ~5-10s (key sync), subsequent runs faster.*

⚠️ Using `access_token` fallback causes key sync conflicts - use dedicated device.

**Device verification** (optional):
```bash
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --timeout 120
# Then start verification from Element: Settings → Security → Sessions
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
│   │   │   ├── matrix-send-e2ee.py      # Send (E2EE) — USE THIS
│   │   │   ├── matrix-read-e2ee.py      # Read (E2EE) — USE THIS
│   │   │   ├── matrix-edit-e2ee.py      # Edit (E2EE) — USE THIS
│   │   │   ├── matrix-send.py           # Send (non-E2EE fallback)
│   │   │   ├── matrix-read.py           # Read (non-E2EE fallback)
│   │   │   ├── matrix-edit.py           # Edit (non-E2EE fallback)
│   │   │   ├── matrix-react.py          # React to messages
│   │   │   ├── matrix-redact.py         # Delete messages
│   │   │   ├── matrix-rooms.py          # List rooms
│   │   │   ├── matrix-resolve.py        # Resolve aliases
│   │   │   ├── matrix-e2ee-setup.py     # E2EE setup
│   │   │   └── matrix-e2ee-verify.py    # Device verification
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
