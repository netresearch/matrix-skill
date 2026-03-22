# Matrix Skill

Agent skill for Matrix chat communication: send/read/edit messages, E2EE support, reactions, threads, and room management.

## Repo Structure

```
├── skills/matrix-communication/
│   ├── SKILL.md                    # Skill metadata and instructions
│   ├── evals/                      # Skill evaluations
│   ├── references/                 # Detailed reference docs (see below)
│   └── scripts/                    # Matrix operation scripts
│       ├── matrix-send-e2ee.py     # Send encrypted messages (primary)
│       ├── matrix-read-e2ee.py     # Read/decrypt messages
│       ├── matrix-edit-e2ee.py     # Edit messages (E2EE)
│       ├── matrix-send.py          # Send (non-E2EE fallback)
│       ├── matrix-read.py          # Read (non-E2EE fallback)
│       ├── matrix-edit.py          # Edit (non-E2EE fallback)
│       ├── matrix-react.py         # React to messages
│       ├── matrix-redact.py        # Delete messages
│       ├── matrix-rooms.py         # List rooms
│       ├── matrix-resolve.py       # Resolve room aliases
│       ├── matrix-e2ee-setup.py    # E2EE device setup
│       ├── matrix-e2ee-verify.py   # Device verification (SAS)
│       ├── matrix-fetch-keys.py    # Fetch E2EE keys
│       ├── matrix-key-backup.py    # Key backup/restore
│       ├── matrix-doctor.py        # Health check / auto-install
│       └── _lib/                   # Shared library code
├── .claude-plugin/
│   └── plugin.json                 # Claude Code plugin manifest
├── commands/
│   └── work-update.md              # Work update command template
├── Build/
│   └── Scripts/                    # Build/validation scripts
├── scripts/
│   └── verify-harness.sh           # Harness consistency checker
├── .github/workflows/              # CI workflows (lint, release, auto-merge)
├── docs/                           # Architecture and planning docs
├── composer.json                   # Composer package manifest
└── README.md
```

## Commands

No build system scripts defined in composer.json. Basic operations:

- `uv run skills/matrix-communication/scripts/matrix-send-e2ee.py ROOM "message"` -- send E2EE message
- `uv run skills/matrix-communication/scripts/matrix-rooms.py` -- list joined rooms
- `uv run skills/matrix-communication/scripts/matrix-read-e2ee.py ROOM` -- read messages
- `python3 skills/matrix-communication/scripts/matrix-doctor.py --install` -- health check
- `bash scripts/verify-harness.sh --status` -- check harness maturity level

## Rules

- Always prefer E2EE scripts (`*-e2ee.py`) over non-E2EE fallbacks
- Room identifiers: use alias (`#room:server`), room ID (`!abc:server`), or short name
- First E2EE run takes ~5-10s for key sync; subsequent runs are faster
- Requires `python3`, `uv`, and Matrix homeserver access
- For E2EE: requires `libolm-dev` system package
- Messages sent appear as the user (not a bot) via access token authentication
- Use `--emote` for /me-style messages, `--thread $eventId` for thread replies

## References

- [SKILL.md](skills/matrix-communication/SKILL.md) -- core skill definition
- [API Reference](skills/matrix-communication/references/api-reference.md)
- [E2EE Guide](skills/matrix-communication/references/e2ee-guide.md)
- [Messaging Guide](skills/matrix-communication/references/messaging-guide.md)
- [Setup Guide](skills/matrix-communication/references/setup-guide.md)
- [Architecture](docs/ARCHITECTURE.md)
