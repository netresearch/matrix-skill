# Architecture

## Overview

The matrix-skill is an Agent Skill package that enables AI coding agents to communicate via the Matrix protocol. It is also packaged as a Claude Code plugin. It follows the [Agent Skills specification](https://agentskills.io) for cross-platform compatibility.

## Skill Structure

The skill uses a script-driven architecture:

1. **SKILL.md** (`skills/matrix-communication/SKILL.md`) -- Entry point loaded by the agent runtime. Contains metadata, quick reference for all operations, and formatting rules.

2. **Scripts** (`skills/matrix-communication/scripts/`) -- Python scripts for each Matrix operation (send, read, edit, react, redact, rooms, resolve, E2EE setup/verify). E2EE variants use `matrix-nio[e2ee]` with libolm for end-to-end encryption. A shared `_lib/` module provides common functionality.

3. **References** (`skills/matrix-communication/references/`) -- Detailed guides for API usage, E2EE configuration, messaging patterns, and initial setup.

## E2EE Architecture

The skill creates a dedicated "Matrix Skill E2EE" device that operates alongside the user's Element client:

```
User's Matrix account
  ├── Element client (primary device)
  └── Matrix Skill E2EE device (agent device)
      ├── matrix-e2ee-setup.py    → initial device/key setup
      ├── matrix-e2ee-verify.py   → SAS emoji verification
      ├── matrix-fetch-keys.py    → fetch missing keys
      └── matrix-key-backup.py    → backup/restore keys
```

Key sync happens on first run (~5-10s). Subsequent operations reuse the established session.

## Plugin Integration

The `.claude-plugin/plugin.json` manifest registers the skill as a Claude Code plugin, enabling slash-command access in addition to automatic skill triggering.

## Distribution

The skill is distributed via multiple channels:
- GitHub releases (`.tar.gz` archives)
- Composer package (`netresearch/matrix-skill`)
- Direct git clone
- npx skills CLI
