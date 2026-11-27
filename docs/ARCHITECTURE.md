<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Architecture

## Overview

The matrix-skill is an Agent Skill package that enables AI coding agents to communicate via the Matrix protocol. It is also packaged as a Claude Code plugin. It follows the [Agent Skills specification](https://agentskills.io) for cross-platform compatibility.

## Skill Structure

The skill uses a script-driven architecture:

1. **SKILL.md** (`skills/matrix-communication/SKILL.md`) -- Entry point loaded by the agent runtime. Contains metadata, quick reference for all operations, and formatting rules.

2. **Scripts** (`skills/matrix-communication/scripts/`) -- Python scripts for each Matrix operation (send, read, edit, react, redact, rooms, resolve, E2EE setup/verify, and the watch daemon plus its reader). The E2EE scripts are stdlib wrappers that translate their flags into a command of [matrix-e2ee-cli](https://github.com/netresearch/matrix-e2ee-cli) (Rust, matrix-sdk) and run it. A shared `_lib/` module provides common functionality, the CLI bootstrap included.

3. **References** (`skills/matrix-communication/references/`) -- Detailed guides for API usage, E2EE configuration, messaging patterns, and initial setup.

## E2EE Architecture

The skill creates a dedicated "Matrix Skill E2EE" device that operates alongside the user's Element client:

```
User's Matrix account
  ├── Element client (primary device)
  └── Matrix Skill E2EE device (agent device)
      ├── matrix-e2ee-setup.py    → matrix-e2ee-cli login / status
      ├── matrix-e2ee-verify.py   → matrix-e2ee-cli verify (SAS emoji)
      ├── matrix-fetch-keys.py    → matrix-e2ee-cli fetch-keys
      └── matrix-key-backup.py    → matrix-e2ee-cli backup-restore / status
```

Key sync happens on first run (~2-5s). Subsequent operations reuse the established session.

**Where the binary comes from.** `_lib/cli.py` maps the platform to a release
asset of matrix-e2ee-cli, keeps it in `<data dir>/matrix-skill/cli/<version>/`
and checks its SHA-256 against `_lib/cli_release.json` before every run; a
missing or differing file is downloaded again, and a download that does not
match the pin is deleted unrun. The pin, not a SHA256SUMS file fetched next to
the binary, is the trust anchor; `Build/Scripts/pin-cli-release.py` writes it
from a release's SHA256SUMS. `MATRIX_E2EE_CLI` names a binary to use as it is.

**One process at a time.** The CLI takes an exclusive lock on its data
directory (`matrix-e2ee-cli/`) for every command that opens the store; a
command that arrives while another holds it waits, then refuses.

**The takeover of the matrix-nio device.** Up to version 4 the device lived in a
matrix-nio store (`matrix-skill/store/`). `_lib/cutover.py` runs before the
first CLI command on a machine that has that store and no CLI session: it takes
the store's lock without waiting, copies the store to an owner-only
`store.backup-<time>`, runs `migrate-nio` (which only reads the store) and
records the takeover in `matrix-skill/nio-migrated.json`. All of that runs
under `matrix-skill/takeover.lock`, and `pending()` is asked again once that
lock is held, so concurrent first commands take over once; the store's own lock
is free while `migrate-nio` runs, because `migrate-nio` takes it itself. An
explicit `matrix-e2ee-cli.py migrate-nio` makes the same backup first. A held
lock or a failed migration stops the command. All of it reports on stderr, because
callers parse the commands' stdout.

## Live Room Awareness

An agent following a room reads a file; it never opens the store.

```
homeserver
    │  sync
    ▼
matrix-watchd.py ──── holds the store, decrypts ────┐
(watch-daemon)                                      │
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

The daemon and its logs are matrix-e2ee-cli's (`watch-daemon`, `watch`, in
`matrix-e2ee-cli/rooms/`); the two scripts run them. The CLI's commands decide
between the socket and the direct path by **connecting to the socket**, never
by testing the lock; `matrix-react.py` and `matrix-redact.py` run the CLI's
`react` and `redact` and so go through the daemon as well. A direct send holds that lock too for its
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
