# Architecture

## Overview

The matrix-skill is an Agent Skill package that enables AI coding agents to communicate via the Matrix protocol. It is also packaged as a Claude Code plugin. It follows the [Agent Skills specification](https://agentskills.io) for cross-platform compatibility.

## Skill Structure

The skill uses a script-driven architecture:

1. **SKILL.md** (`skills/matrix-communication/SKILL.md`) -- Entry point loaded by the agent runtime. Contains metadata, quick reference for all operations, and formatting rules.

2. **Scripts** (`skills/matrix-communication/scripts/`) -- Python scripts for each Matrix operation (send, read, edit, react, redact, rooms, resolve, E2EE setup/verify, and the watch daemon plus its reader). E2EE variants use `matrix-nio[e2ee]` with libolm for end-to-end encryption. A shared `_lib/` module provides common functionality.

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
      └── matrix-key-backup.py    → restore keys from the server-side backup
```

Key sync happens on first run (~2-5s). Subsequent operations reuse the established session.

**One process at a time.** Two `matrix-nio` processes on one store corrupt it, and
the corruption does not announce itself: it surfaces later as a message nobody can
decrypt, or a store that no longer opens. Every path that opens the store takes an
exclusive `flock` on the store directory, held until the process exits. A command
that arrives while another holds it waits, then refuses and names the holder's pid.

**The pin is part of the format.** `matrix-nio[e2e]<0.26` is pinned in every script
that imports nio. 0.26 changed the crypto backend, and the two backends write
incompatible stores — so the pin and the store on disk belong together, and moving
one means recreating the other.

## Live Room Awareness

An agent following a room reads a file; it never opens the store.

```
homeserver
    │  sync
    ▼
matrix-watchd.py ──── holds the store, decrypts ────┐
    │  appends                                       │  Unix socket
    ▼                                                │  send · react · redact · edit
rooms/<slug>.jsonl ──── tail ────► matrix-watch.py   │
    │                                  │             │
    └─ rooms/index.md (OKF bundle)     └─ one line per event on stdout
```

The daemon is the only process that holds the store while it runs, which is also
why it is the only one that syncs: a Matrix sync is account-wide and consumes the
to-device events — room keys, verification requests — for every other process on
that device.

Commands decide between the socket and the direct path by **connecting to the
socket**, never by testing the lock. A direct send holds that lock too for its
couple of seconds; deciding on it would aim a command at a socket nobody serves.

Design and implementation plan: [`docs/specs/`](specs/) and
[`docs/exec-plans/completed/`](exec-plans/completed/).

## Plugin Integration

The `.claude-plugin/plugin.json` manifest registers the skill as a Claude Code plugin, enabling slash-command access in addition to automatic skill triggering.

## Distribution

The skill is distributed via multiple channels:
- GitHub releases (`.tar.gz` archives)
- Composer package (`netresearch/matrix-skill`)
- Direct git clone
- npx skills CLI
