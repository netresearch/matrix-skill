# Matrix Skill

A Claude Code skill for Matrix chat communication.

## Overview

This skill enables Claude Code to send messages to Matrix chat rooms on behalf of users. Messages are sent using the user's own access token, so they appear as coming from the user. Works with any Matrix homeserver.

## Features

- **Send messages** to any joined Matrix room
- **Markdown support** for formatted messages
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
uv run scripts/matrix-send.py "#ops:netresearch.de" "Deployment complete!"

# By room ID
uv run scripts/matrix-send.py "!abc123:netresearch.de" "Hello!"

# With markdown formatting
uv run scripts/matrix-send.py "#dev:netresearch.de" "**Build passed** for commit abc123"
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
uv run scripts/matrix-read.py "#test:netresearch.de"

# Read more messages
uv run scripts/matrix-read.py "#test:netresearch.de" --limit 50
```

### Resolve Room Alias

```bash
uv run scripts/matrix-resolve.py "#test:netresearch.de"
```

## E2EE Support

| Version | Sending | Reading |
|---------|---------|---------|
| **v1** (current) | Works (if room allows unverified devices) | Unencrypted only |
| v2 (planned) | Same | Full unencrypted support |
| v3 (future) | Full E2EE | Full E2EE |

## Structure

```
netresearch-matrix-skill/
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
