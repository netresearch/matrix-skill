# E2EE (End-to-End Encryption) Guide

Detailed guide for Matrix E2EE setup, device verification, and key management.

## Which Script to Use?

| Scenario | Script | Notes |
|----------|--------|-------|
| Unencrypted room | `matrix-send.py` | Fast, no deps |
| E2EE room with "allow unverified" | `matrix-send.py` | Works but not encrypted |
| E2EE room, proper encryption | `matrix-send-e2ee.py` | Requires libolm + setup |

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
store, never on the server in usable form. Point matrix-nio at Element's token
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
`credentials.json`.

## E2EE Script Usage

```bash
# First run after setup syncs keys (~2-5s)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Secret message'

# Subsequent runs faster (uses cached keys)
uv run skills/matrix-communication/scripts/matrix-send-e2ee.py '#encrypted-room:server' 'Another message'
```

Storage locations:
- Device credentials: `~/.local/share/matrix-skill/store/credentials.json`
- Encryption keys: `~/.local/share/matrix-skill/store/*.db`

## Device Verification

Device verification marks a device as trusted and enables automatic key sharing.

```bash
# Auto-find Element device and initiate verification
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --timeout 180

# Target specific device
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --request DEVICE_ID --timeout 180

# With debug output
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --debug --timeout 180
```

**Smart device selection:** Automatically prioritizes Element clients (Desktop/Android/iOS) over backup devices that can't respond interactively. Without `--request` it picks a device on its own and may well pick the wrong one — a phone that is not the client you are sitting in front of. Run `--list` and name the device.

`--listen` is the other direction: wait for Element to start the verification instead of sending a request. Use it when Element already shows "Start verification on the other device", which means it is waiting for this side to accept.

### A fresh device cannot verify until its keys are queried

Right after `matrix-e2ee-setup.py` the store knows no other devices, and
verification fails on an error that names the wrong thing:

```
Error accepting: Key verification with the transaction id <id> does not exist.
```

nio cannot build a SAS object for a device it has no keys for. It only queries
users it has marked as changed, and a new store has marked nobody — `--debug`
reports `Keys query: No key query required.` while the device list is empty.
Force one query for your own user before verifying.

### Live awareness: one daemon owns the store

`matrix-watchd.py` holds an exclusive lock on the store for its whole run,
syncs, decrypts, and appends every event of a watched room to
`~/.local/share/matrix-skill/rooms/<slug>.jsonl`. It is the only process that
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

**Send, react and redact need no new flags.** They try the daemon's socket and
fall back to the direct path when nothing answers. The signal is a socket that
answers, never the store lock: a direct send holds that lock too for a couple
of seconds, and deciding on it would route a command into a socket nobody
serves.

Two things worth knowing before relying on it:

- The daemon is the account's syncer while it runs. That is the point - whoever
  syncs consumes the to-device events, so having one owner is what keeps room
  keys from landing wherever a race puts them.
- A revoked token stops it, and it writes the reason into every watched log
  first. A watcher that dies quietly is indistinguishable from a quiet room.

### The nio pin and the store belong together

The scripts pin `matrix-nio[e2e]<0.26`. That is not cosmetic:

- 0.26 sends the SAS commitment as a hex digest where 0.25 sent unpadded base64,
  so Element rejects every verification before it shows emoji
  (matrix-nio/matrix-nio#570)
- the two releases use different crypto backends (libolm vs vodozemac) and write
  incompatible stores — opening one with the other fails as `BAD_ACCOUNT_KEY`,
  which reads like a credential problem and is not one

Moving the pin is therefore a migration, not a version bump:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py --logout
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-setup.py          # new device
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-key-backup.py --import-keys
uv run ${CLAUDE_SKILL_DIR}/scripts/matrix-e2ee-verify.py --request DEVICE
```

Run every step on the same pin. One command from an unpinned checkout reopens
the store on the other backend and rewrites its account.

### Agent Workflow for Real-Time Emoji Display

The verification script writes emojis to `/tmp/matrix_verification_emojis.txt` for agent polling.

**Step 1: Clear emoji file and start verification in background**
```bash
rm -f /tmp/matrix_verification_emojis.txt
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --timeout 180 > /tmp/verify_log.txt 2>&1 &
```

**Step 2: Poll for emojis and show to user immediately**
```bash
for i in {1..30}; do
    if [ -f /tmp/matrix_verification_emojis.txt ]; then
        cat /tmp/matrix_verification_emojis.txt
        break
    fi
    sleep 1
done
```

**Step 3: Tell user to confirm in Element**
- "Compare these emojis with what Element shows"
- "Click 'They match' in Element to complete verification"

**Step 4: Wait for verification to complete**
```bash
grep -q "VERIFICATION SUCCESSFUL" /tmp/verify_log.txt && echo "Verified!"
```

### Why Verify?
- Removes "unverified device" warnings for other users
- Enables automatic room key sharing from other devices
- Required for some security-conscious rooms

### Gate trust on the verification result — never trust unconditionally

**Security rule:** only persist trust in a device *after* the SAS/emoji check
has cryptographically passed. Calling `client.verify_device(...)` unconditionally
marks the device trusted even on a MAC mismatch — that is a security bypass (a
MITM device gets stored as trusted).

What makes this subtle in matrix-nio:

- `sas.receive_mac_event(...)` **never raises** on a bad MAC — it silently moves
  the SAS to `SasState.canceled`. A bare `try/except` around it therefore catches
  nothing and is not a safety check.
- `sas.verified` can be `False` even after a *successful* MAC exchange, due to a
  race in nio's state machine, so it cannot by itself distinguish a genuine
  mismatch from the benign race. A device id appears in `sas.verified_devices`
  only once its MAC is cryptographically validated, and a later cancel does not
  clear it — so that set is the authoritative "MACs matched" signal.

The correct flow (as fixed in `matrix-e2ee-verify.py`):

1. On a genuine mismatch (`not sas.verified and device not in sas.verified_devices`),
   send `m.key.verification.cancel`, report failure, and do **not** trust.
2. Only when `sas.verified` is strictly `True`, call `client.verify_device(sas.other_olm_device)` —
   nio's `Sas` never persists trust itself.

This bypass was caught by the automated commit security review (2026-06-27) and
re-gated on `sas.verified` in
[#48](https://github.com/netresearch/matrix-skill/pull/48).

## matrix-nio API notes (0.25.2)

Maintainer notes for the E2EE scripts. Verified against matrix-nio 0.25.2 (the
version installed for this skill — `importlib.metadata.version("matrix-nio")`):

| What you might reach for | Reality (matrix-nio 0.25.2) |
|--------------------------|-----------------------------|
| `nio.__version__` | Does **not** exist — accessing it raises `AttributeError`. Read the version from package metadata instead: `from importlib.metadata import version; version("matrix-nio")`. |
| `from nio.store import DeviceStore` | Wrong path — raises `ImportError`. `DeviceStore` lives in `nio.crypto`: `from nio.crypto import DeviceStore`. |
| `device.id` | Works — it is a read-only property aliasing `device_id` (returns `self.device_id`). It does **not** raise `AttributeError`, but always prefer the canonical `device_id` attribute for robustness against future library changes. |

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

The `matrix-key-backup.py` script handles the full workflow: SSSS decryption → backup key derivation → session key decryption → import into local store.

```bash
# Check backup status
uv run skills/matrix-communication/scripts/matrix-key-backup.py --status

# Restore using recovery key AND import into local store
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj qRGp YB4C ..." --import-keys

# Restore using passphrase AND import
uv run skills/matrix-communication/scripts/matrix-key-backup.py --passphrase "your recovery passphrase" --import-keys
```

**Important:** The `--import-keys` flag is required to actually import decrypted session keys into your local store. Without it, keys are only displayed but not saved.

Find your recovery key in Element: Settings → Security & Privacy → Secure Backup → "Show Recovery Key"

**Note:** matrix-nio does not natively support server-side key backup (see [matrix-nio#218](https://github.com/matrix-nio/matrix-nio/issues/218)). The `matrix-key-backup.py` script implements this manually using the Matrix API directly.

### Verification with `--listen` Mode

The verification script supports waiting for incoming verification requests:

```bash
# Listen for incoming verification requests (e.g., from Element)
uv run skills/matrix-communication/scripts/matrix-e2ee-verify.py --timeout 180

# The script will:
# 1. Sync with server
# 2. Auto-detect Element devices
# 3. Initiate or accept verification
# 4. Display emoji for comparison
# 5. Write emojis to /tmp/matrix_verification_emojis.txt for agent polling
```

**Element X compatibility:** Element X uses different verification flows that may not be fully compatible. Use Element Desktop or Element Android for verification.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `[Unable to decrypt]` | Missing session keys | Restore from backup with `--import-keys` |
| `MAC verification failed` | Wrong recovery key or passphrase | Verify recovery key from Element settings |
| `PkDecryption` errors | libolm version mismatch | Update libolm: `apt install libolm-dev` |
| Script hangs silently | stdout buffering in non-interactive context | Fixed in scripts (line_buffering=True) |
| Verification times out | No compatible device responding | Use Element Desktop, not Element X |
| `signature verification failed` | Reusing Element's device | Use dedicated device via `matrix-e2ee-setup.py` |

## Limitations

- **First sync**: Initial run ~2-5s for key exchange; subsequent runs ~2-3s
- **Device trust**: Auto-trusts devices (TOFU model)
- **Setup required**: First use requires user's Matrix password (one-time only)
- **Verification**: Cross-signing/room-based verification not fully supported by matrix-nio
- **Key backup**: Requires recovery key or passphrase (found in Element settings)
- **matrix-nio limitation**: No native server-side key backup support — `matrix-key-backup.py` works around this via direct API calls
