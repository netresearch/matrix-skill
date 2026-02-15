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

**Access token fallback (not recommended):** Using `access_token` from config reuses Element's device, causing key sync issues and verification problems. Only use if password-based setup isn't possible.

## E2EE Script Usage

```bash
# First run after setup is slow (~5-10s) - syncs keys
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

**Smart device selection:** Automatically prioritizes Element clients (Desktop/Android/iOS) over backup devices that can't respond interactively.

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

## Reading E2EE Messages

```bash
# Read recent encrypted messages
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py '#room:server' --limit 10

# JSON output
uv run skills/matrix-communication/scripts/matrix-read-e2ee.py '#room:server' --json
```

**Note:** Messages sent before your device was created show as `[Unable to decrypt]` -- this is normal E2EE behavior.

## Fetching Missing Keys

### Method 1: Request from Other Devices (Recommended)

After device verification, other devices can forward keys automatically:

```bash
# Fetch keys for a specific room
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py ROOM --sync-time 60

# Extended wait for more keys
uv run skills/matrix-communication/scripts/matrix-fetch-keys.py IT --limit 200 --sync-time 120
```

Requirements: device must be verified, other verified devices must be online.

### Method 2: Restore from Server Backup

If key forwarding doesn't work (no other devices online):

```bash
# Check backup status
uv run skills/matrix-communication/scripts/matrix-key-backup.py --status

# Restore using recovery key
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj qRGp YB4C ..."

# Restore using passphrase
uv run skills/matrix-communication/scripts/matrix-key-backup.py --passphrase "your recovery passphrase"
```

Find your recovery key in Element: Settings > Security & Privacy > Secure Backup > "Show Recovery Key"

## Limitations

- **Old messages**: Can't decrypt without key backup restoration
- **First sync**: Initial run is slow due to key exchange
- **Device trust**: Auto-trusts devices (TOFU model)
- **Setup required**: First use requires user's Matrix password (one-time only)
- **Verification**: Experimental -- cross-signing/room-based verification not fully supported
- **Key backup**: Requires recovery key/passphrase (stored in Element settings)
