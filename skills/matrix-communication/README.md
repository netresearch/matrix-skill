# Matrix Communication

Send and receive messages in Matrix chat rooms with full E2EE encryption support.

## Features

- **E2EE Encryption** - Full end-to-end encryption support
- **Send Messages** - Post to any joined room with markdown formatting
- **Read Messages** - Decrypt and read encrypted messages
- **Edit Messages** - Modify existing messages
- **Reactions** - Add emoji reactions (✅ 👍 🚀)
- **Redact** - Delete messages
- **Room Management** - Create rooms, invite users, manage power levels
- **Bot Prefix** - Optional 🤖 prefix for automated messages

## Installation

### Option 1: Via Netresearch Marketplace (Recommended)

```bash
/plugin marketplace add netresearch/claude-code-marketplace
```

Then install with `/install-plugin netresearch/matrix-skill`

### Option 2: Download Release

Download the [latest release](https://github.com/netresearch/matrix-skill/releases/latest) and extract to `~/.claude/skills/matrix-communication/`

## Usage

The skill triggers automatically on:
- Room references: `#room:server`, `!roomid:server`
- Chat requests: "send to matrix", "post in chat"
- Matrix URLs: `https://matrix.*/`, `https://element.*/`

### Setup

Just ask:
> "Set up the Matrix skill for me"

The agent guides you through homeserver, user ID, and E2EE device creation.

### Example Prompts

```
"Send 'Deployment complete!' to #ops:matrix.org"
"Read the last 10 messages from #dev:matrix.org"
"React with ✅ to the last message in #support"
```

## Structure

```
matrix-communication/
├── SKILL.md              # AI instructions
├── README.md             # This file
├── scripts/              # All Matrix scripts
│   ├── matrix-send-e2ee.py
│   ├── matrix-read-e2ee.py
│   ├── matrix-edit-e2ee.py
│   └── ...
└── references/
    └── api-reference.md
```

## References

- `references/api-reference.md` - Matrix API endpoints

## License

MIT License - See [LICENSE](../../LICENSE) for details.

## Credits

Developed and maintained by [Netresearch DTT GmbH](https://www.netresearch.de/).

---

**Made with ❤️ for Open Source by [Netresearch](https://www.netresearch.de/)**
