<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# E2EE (End-to-End Encryption) Guide

Detailed guide for Matrix E2EE setup, device verification, and key management.

## Which Script to Use?

| Scenario | Script | Notes |
|----------|--------|-------|
| Any room | `matrix-send-e2ee.py` | Encrypted when the room is; requires setup; downloads matrix-e2ee-cli on first use |
| Any room, older options only | `matrix-send.py` | The same matrix-e2ee-cli command, so the same setup |
| A bot that cannot decrypt (hookshot without encryption) | `matrix-send-e2ee.py --plaintext` | Unencrypted even in an encrypted room: the homeserver and later members can read it ([hookshot-integration.md](hookshot-integration.md)) |

## E2EE Setup

**Use a dedicated device** -- this avoids key sync conflicts with Element:

```bash
# One-time setup: create dedicated E2EE device

# Option 1: Environment variable (recommended - handles special chars)
MATRIX_PASSWORD="YOUR_PASSWORD" uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py

# Option 2: Interactive prompt (secure - password not in history)
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py

# Now send encrypted messages
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py '#room:server' 'Encrypted message'

# Check setup status
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py --status
```

**Why dedicated device?**
- Clean key state, no conflicts with Element
- Proper cross-signing setup
- Avoids "signature verification failed" errors

### ⛔ Never point the E2EE scripts at another client's token

There is no access-token fallback. Earlier revisions of this guide offered one
"if password-based setup isn't possible" — that advice was wrong and is retracted.

A Matrix access token is bound to a `device_id`, and E2EE state is per device:
the olm identity and the megolm session keys live in each client's own local
store, never on the server in usable form. Point the skill at Element's token
and two independent clients now act as one device. Neither can read what the
other encrypts.

What that looks like in practice:

- Element shows `[Unable to decrypt]` **for messages you just sent yourself**
- restarting Element appears to fix it (it refetches from key backup), then it
  returns
- other people in the room may see your device as changed or unverified
- nothing fails at the moment you paste the token — the writes succeed

Recovery is a logout of the affected client and a fresh login, plus a key-backup
restore. That is disruptive on a client you actually use.

The correct move in every case, including "I already have a token":

```bash
MATRIX_PASSWORD="YOUR_PASSWORD" uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py
```

No password available? Then E2EE is not set up — say so and stop. A borrowed
token is not a workaround, it is damage to someone's running session.

`matrix-doctor.py` enforces this: it asks the homeserver which device the stored
credential belongs to and fails `e2ee_setup` when that is not the device in
matrix-e2ee-cli's `session.json`.

## E2EE Script Usage

```bash
# First run after setup syncs keys (~2-5s)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Secret message'

# Subsequent runs faster (uses cached keys)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Another message'
```

Every E2EE script is a thin wrapper around
[matrix-e2ee-cli](https://github.com/netresearch/matrix-e2ee-cli) (Rust,
matrix-sdk). The wrapper downloads the release binary pinned in
`scripts/_lib/cli_release.json` on first use and checks its SHA-256 before
every run; `MATRIX_E2EE_CLI=/path/to/binary` uses a binary of your own instead.
Commands no wrapper covers (`logout`, `migrate-nio`, `verify --hand-over`,
`--confirm`, `--cancel`) run through `matrix-e2ee-cli.py`, which passes its
arguments on unchanged. Before an explicit `migrate-nio` it copies the store
named by `--store` (default `matrix-skill/store/`) the same way as the
automatic takeover below, and records a successful run.

Storage locations (`$XDG_DATA_HOME` when set, else `~/.local/share`):
- Session (user, device, access token, store passphrase), owner-only: `matrix-e2ee-cli/session.json`
- Encryption keys: `matrix-e2ee-cli/store/`
- The binary: `matrix-skill/cli/<version>/` (on macOS without `XDG_DATA_HOME`: `~/Library/Application Support/matrix-skill/cli/<version>/`)

### Moving from matrix-nio (version 4 and older)

Up to version 4 the skill kept its device in a matrix-nio store,
`matrix-skill/store/` with `credentials.json`. The first E2EE command on a
machine that still has that store, and no matrix-e2ee-cli session yet, takes the
device over once, before it runs. It holds `matrix-skill/takeover.lock` from
start to end, so two commands started together take the device over once: the
second waits, then finds the takeover done.

1. it stops when the old store is in use (an old `matrix-watchd.py` still
   running holds its lock): stop that process and run the command again,
2. it copies the whole store, `credentials.json` included, to
   `matrix-skill/store.backup-<UTC time>` (owner-only: the copy holds the
   access token); a retry after a failed takeover reuses the newest copy while
   the store's files are unchanged,
3. it runs `matrix-e2ee-cli migrate-nio`, which only reads the old store and
   keeps the device id, its identity keys (so its verification stays valid),
   its room keys and nio's local trust of other devices,
4. it records the takeover in `matrix-skill/nio-migrated.json`, so a later
   `logout` never leads to a second takeover.

Everything it prints goes to stderr. When `migrate-nio` fails, the command does
not run, and the old store is unchanged. Afterwards:

- Run `matrix-key-backup.py --import-keys` once: it imports the cross-signing
  keys and the room keys of the server-side backup.
- `migrate-nio` suggests retiring the old copy with `matrix-e2ee-setup.py
  --logout`. That flag is refused now. Keep `matrix-skill/store/` until the
  takeover has succeeded and the new device works; only then delete it
  yourself, if you want to. Never log the device out on the server
  (`matrix-e2ee-cli.py logout`): that ends the migrated device too.
- Do not run an older version of this skill on the same machine: it would open
  the old store as the same device, and the two copies break each other's
  decryption.

## Device Verification

Device verification marks a device as trusted and enables automatic key sharing.

```bash
# List your devices, then name the one to verify with
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --list
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --request DEVICE_ID --timeout 180

# Or let Element start it
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --listen --timeout 180
```

The device is no longer picked automatically: run `--list` and name it. With
`--request` and `--listen` the CLI shows the emoji on the terminal and asks
there whether they match, so both need a terminal on stdin and stderr. An agent
has none and uses the hand-over flow below.

`--listen` is the other direction: wait for Element to start the verification instead of sending a request. Use it when Element already shows "Start verification on the other device", which means it is waiting for this side to accept.

### Live awareness: one daemon owns the store

`matrix-watchd.py` runs `matrix-e2ee-cli watch-daemon`. It holds an exclusive
lock on the store for its whole run, syncs, decrypts, and appends every event of
a watched room to `~/.local/share/matrix-e2ee-cli/rooms/<slug>.jsonl` (its
output goes to `daemon.log` beside it). It is the only process that
opens the store while it runs.

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watchd.py --start
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-watch.py '#room:server'
```

Rooms come from `watch_rooms` in the config. Alongside the logs the daemon
writes an OKF bundle - `index.md` plus one typed page per room - so the mapping
from slug to room is readable rather than an internal detail.

`matrix-watch.py` reads a file and never opens the store, so any number can run
at once and none of them can disturb a send.

**Send, edit, react and redact need no new flags.** They try the
daemon's socket and fall back to the direct path when nothing answers. The
signal is a socket that answers, never the store lock: a direct send holds that
lock too for a couple of seconds, and deciding on it would route a command into
a socket nobody serves.

Two things worth knowing before relying on it:

- The daemon is the account's syncer while it runs. That is the point - whoever
  syncs consumes the to-device events, so having one owner is what keeps room
  keys from landing wherever a race puts them.
- A revoked token stops it, and it writes the reason into every watched log
  first. A watcher that dies quietly is indistinguishable from a quiet room.

### Agent workflow: verification without a terminal

`--hand-over` lets another process confirm. The waiting process prints the
emoji as one JSON line with a `token` and never confirms on its own:

**Step 1: start the verification in the background**
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-cli.py verify --listen --hand-over --timeout 180 > /tmp/verify.out 2>&1 &
```
(or `verify --request DEVICE --hand-over`). The person then starts the
verification in Element from the session they sit in (Settings → Sessions →
the agent's device → Verify session).

**Step 2: show the emoji line to the person** as soon as it appears in
`/tmp/verify.out`, and ask them to compare it with Element.

**Step 3: only after they said the emoji match:**
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-cli.py verify --confirm TOKEN
```
Otherwise `verify --cancel TOKEN`. TOKEN is the `token` of the line the person
saw; it names that comparison and no other. The data directory's file system
must support hard links.

### Why Verify?
- Removes "unverified device" warnings for other users
- Enables automatic room key sharing from other devices
- Required for some security-conscious rooms

## Reading E2EE Messages

```bash
# Read recent encrypted messages
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py '#room:server' --limit 10

# JSON output for programmatic analysis
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py '#room:server' --json
```

**First run** (~2-5s) — the client syncs keys with the server.

### Understanding `[Unable to decrypt]`

Messages showing `[Unable to decrypt]` mean your device lacks the Megolm session keys for those messages. This is **not** permanent — keys can be recovered:

| Situation | Solution |
|-----------|----------|
| Messages sent before device was created | Restore from server-side key backup |
| Messages from before verification | Verify device, then request key forwarding |
| No other devices online | Use key backup with recovery key/passphrase |

**Decision tree:**
1. Have you verified your device? → If no, verify first (see above)
2. Are other verified devices online? → Try `matrix-fetch-keys.py` (Method 1)
3. Do you have a recovery key/passphrase? → Try `matrix-key-backup.py` (Method 2)

## Fetching Missing Keys

### Method 1: Request from Other Devices

After device verification, other devices can forward keys automatically:

```bash
# Fetch keys for a specific room
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py ROOM --sync-time 60

# Extended wait for more keys
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py IT --limit 200 --sync-time 120
```

Requirements: device must be verified, other verified devices must be online.

### Method 2: Restore from Server Backup (Recommended for old messages)

`matrix-key-backup.py --import-keys` runs `matrix-e2ee-cli backup-restore`: it imports the secrets of the secret storage (the cross-signing keys among them) with the recovery key or passphrase, then downloads the room keys of every joined encrypted room from the server-side backup. Rooms the account has left get no keys; after rejoining one, run `--import-keys` again to read its history.

```bash
# Check backup status (matrix-e2ee-cli status)
uv run skills/matrix-communication/scripts/matrix-key-backup.py --status

# Restore; prompts for the recovery key or the passphrase
uv run skills/matrix-communication/scripts/matrix-key-backup.py --import-keys

# Non-interactive: from the environment instead of a prompt
MATRIX_RECOVERY_KEY="..." uv run skills/matrix-communication/scripts/matrix-key-backup.py --import-keys
```

The recovery key and passphrase are not accepted as command-line values: other local users can read those in the process list. `--allow-secret-argument` restores that for scripts that can use neither a prompt nor the environment.

**Important:** `--import-keys` is what restores the keys. Without it (and without `--status`) the script refuses: the CLI has no mode that only displays them. With both flags, `--status` wins and nothing is imported. Every run asks for the recovery key or passphrase (environment or prompt).

Find your recovery key in Element: Settings → Security & Privacy → Secure Backup → "Show Recovery Key"

### Verification with `--listen` Mode

The verification script supports waiting for incoming verification requests:

```bash
# Listen for incoming verification requests (e.g., from Element)
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --listen --timeout 180

# The script will:
# 1. Sync with server
# 2. Wait for the other client to start the verification
# 3. Accept the request and show the emoji, then ask on the terminal whether they match
```

Only verification requests from devices of your own account are answered;
`--accept-from` for another user's devices is not supported any more.

Prefer `--listen` over `--request` whenever the account has several active
client sessions (`--list` showing more than one "Element Desktop" entry is the
typical case): with `--request` you would have to guess which device to
target — a request sent to a session that is not open just times out — while
with `--listen` the user starts the verification in Element from exactly the
session they are sitting in (Settings → Sessions → the agent's device →
Verify session).

**Element X compatibility:** Element X uses different verification flows that may not be fully compatible. Use Element Desktop or Element Android for verification.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `[Unable to decrypt]` | Missing session keys | Restore from backup with `--import-keys` |
| `MAC verification failed` | Wrong recovery key or passphrase | Verify recovery key from Element settings |
| Verification times out | No compatible device responding | Use Element Desktop, not Element X |
| `signature verification failed` | Reusing Element's device | Use dedicated device via `matrix-e2ee-setup.py --force` |

## Limitations

- **First sync**: Initial run ~2-5s for key exchange; subsequent runs ~2-3s
- **Device trust**: Room keys go only to verified devices. A send into a room with unverified devices is refused and lists them; verify them, or pass `--trust-unverified-devices` to share that one message's key with them. The flag is not stored and never marks a device verified. Devices marked "ignored" (what the daemon of version 3.1.8 or older stored) count as unverified. Stores used with version 3.1.8 or older can also contain devices that the direct send and edit scripts of those versions marked verified without a check, and the takeover from matrix-nio carries that local trust over; to start from a clean trust state, re-create the device (`matrix-e2ee-cli.py logout`, which also ends it on the server, then `matrix-e2ee-setup.py`) and verify your own devices again
- **Setup required**: First use requires user's Matrix password (one-time only)
- **Key backup**: Requires recovery key or passphrase (found in Element settings)
