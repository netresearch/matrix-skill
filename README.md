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
- **Visual effects** - Confetti 🎉, fireworks 🎆, snowfall ❄️ (Element clients)
- **List rooms** to find the right destination
- **Read messages** (unencrypted messages only in v1)

## Prerequisites

### Configuration

Create `~/.config/matrix/config.json`:

```json
{
  "homeserver": "https://matrix.org",
  "access_token": "syt_..."
}
```

**Get your access token:**
1. Open Element
2. Go to Settings → Help & About
3. Scroll to "Access Token"
4. Copy the token (starts with `syt_`)

### File Permissions

```bash
chmod 600 ~/.config/matrix/config.json
```

## Installation

### Via Claude Code Marketplace

The skill is available in the Netresearch skill marketplace.

### Manual

Clone this repository and reference the skill in your Claude configuration.

## Usage

### Send a Message

```bash
# By room alias
uv run scripts/matrix-send.py "#myroom:matrix.org" "Deployment complete!"

# By room ID
uv run scripts/matrix-send.py "!abc123:matrix.org" "Hello!"

# With markdown formatting
uv run scripts/matrix-send.py "#dev:matrix.org" "**Build passed** for commit abc123"
```

### List Joined Rooms

```bash
# List all rooms
uv run scripts/matrix-rooms.py

# Search for specific room
uv run scripts/matrix-rooms.py --search ops
```

### Read Messages

```bash
# Read last 10 messages
uv run scripts/matrix-read.py "#myroom:matrix.org"

# Read more messages
uv run scripts/matrix-read.py "#myroom:matrix.org" --limit 50
```

### Resolve Room Alias

```bash
uv run scripts/matrix-resolve.py "#myroom:matrix.org"
```

## E2EE Support

**Current status:**
- **Sending**: Works to E2EE rooms (if room allows unverified devices)
- **Reading**: Unencrypted messages only (API-sent, webhooks, bots)

**Roadmap:**
- Improved read support for unencrypted rooms
- Full E2EE with Megolm key management (requires matrix-nio or similar SDK)

## Structure

```
matrix-skill/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── scripts/
│   ├── matrix-send.py           # Send messages
│   ├── matrix-rooms.py          # List joined rooms
│   ├── matrix-read.py           # Read messages
│   └── matrix-resolve.py        # Resolve room aliases
├── skills/
│   └── matrix-communication/
│       ├── SKILL.md             # Skill instructions
│       └── references/
│           └── api-reference.md # Matrix API reference
├── LICENSE
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE)

## Author

Netresearch DTT GmbH - https://www.netresearch.de
