# Matrix Skill

An Agentic Skill for Matrix chat communication, distributed as a Claude Code plugin.

## Overview

This skill enables AI coding agents to send messages to Matrix chat rooms on behalf of users. Messages are sent using the user's own access token, so they appear as coming from the user. Works with any Matrix homeserver.

**What is an Agentic Skill?** Platform-agnostic instructions and tools that AI coding agents can use. This skill is packaged as a Claude Code plugin but follows the open [Agentic Skills specification](https://github.com/anthropics/agentic-skills).

## Features

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

## Installation & Setup

### 1. Install the Skill

```bash
# Via Netresearch marketplace
/install-plugin netresearch/matrix-skill

# Or manually
/install-plugin https://github.com/netresearch/matrix-skill
```

### 2. Let the Agent Configure It

Just ask:
> "Set up the Matrix skill for me"

The agent will guide you through:
- Your Matrix homeserver URL
- Your Matrix user ID
- Your Matrix password (for E2EE device, used once, not stored)
- Optional bot prefix (e.g., 🤖)

### 3. Done!

Start using it:
> "Send 'Hello!' to #general:matrix.org"

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

## Structure

```
matrix-skill/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── skills/
│   └── matrix-communication/
│       ├── SKILL.md             # Skill instructions
│       ├── scripts/
│       │   ├── matrix-send-e2ee.py      # Send (E2EE) - USE THIS
│       │   ├── matrix-read-e2ee.py      # Read (E2EE) - USE THIS
│       │   ├── matrix-edit-e2ee.py      # Edit (E2EE) - USE THIS
│       │   ├── matrix-send.py           # Send (non-E2EE fallback)
│       │   ├── matrix-read.py           # Read (non-E2EE fallback)
│       │   ├── matrix-edit.py           # Edit (non-E2EE fallback)
│       │   ├── matrix-react.py          # React to messages
│       │   ├── matrix-redact.py         # Delete messages
│       │   ├── matrix-rooms.py          # List rooms
│       │   ├── matrix-resolve.py        # Resolve aliases
│       │   ├── matrix-e2ee-setup.py     # E2EE setup
│       │   └── matrix-e2ee-verify.py    # Device verification
│       └── references/
│           └── api-reference.md
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
