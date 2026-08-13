# Matrix Skill Setup Guide

Complete setup walkthrough for the Matrix communication skill.

## Prerequisites

Before using E2EE features, check dependencies:

```bash
# Run health check (checks all dependencies)
python3 skills/matrix-communication/scripts/matrix-doctor.py

# Auto-install missing dependencies
python3 skills/matrix-communication/scripts/matrix-doctor.py --install

# Skip the homeserver call (air-gapped / CI): the token row then reads
# 'not verified' instead of OK, and the summary says so
python3 skills/matrix-communication/scripts/matrix-doctor.py --offline
```

The `token` row asks the homeserver (`GET /_matrix/client/v3/account/whoami`)
whether the config token actually works, because a revoked or expired token
leaves the config file perfectly well-formed. It has three outcomes:

| row | meaning |
| --- | --- |
| `[OK] token` | the homeserver accepted it and it belongs to the configured `user_id` |
| `[FAIL] token` | the homeserver rejected it (HTTP 401 `M_UNKNOWN_TOKEN`) — log in again and replace it |
| `[??] token` | nothing was verified: no token in the config (normal for E2EE, which uses the credentials store), `--offline`, or the homeserver was unreachable |

`[??]` is deliberately not `OK`: the summary then reads "Checks passed, except
token — could not be verified" rather than "All checks passed", so a passing
doctor never implies a working credential.

**Required for E2EE:**
- `matrix-nio[e2e]` - Matrix client library with encryption support
- `libolm` - Olm encryption library, bundled and compiled by `python-olm` (Linux installs a pre-built wheel; **macOS 26+ is unsupported**, see Troubleshooting)

**Package manager priority:** The doctor script tries: `uvx pip` > `uv pip` > `pip` > `pip3`

## Setup Steps

### Step 1: Check if already configured

```bash
cat ~/.config/matrix/config.json 2>/dev/null && echo "Config exists" || echo "Not configured"
```

### Step 2: Gather information

Ask user for:
1. **User ID** - e.g., `@username:matrix.org` or `@username:company.com`
2. **Matrix password** - for E2EE device creation (not stored, used once)
3. **Bot prefix** (optional) - e.g., bot emoji to mark automated messages

### Step 3: Discover homeserver URL

Extract the domain from the user ID and discover the homeserver via `.well-known`:

```bash
# Extract domain from user ID (e.g., @user:example.com -> example.com)
MATRIX_DOMAIN="DOMAIN_FROM_USER_ID"

# Discover homeserver URL
curl -s "https://${MATRIX_DOMAIN}/.well-known/matrix/client" | python3 -c "import sys,json; print(json.load(sys.stdin)['m.homeserver']['base_url'])"
```

**Example:** For `@sebastian.mendel:netresearch.de`:
- Domain: `netresearch.de`
- Discovery URL: `https://netresearch.de/.well-known/matrix/client`
- Returns homeserver: `https://matrix.netresearch.de`

### Step 4: Create config file

```bash
mkdir -p ~/.config/matrix
cat > ~/.config/matrix/config.json << 'EOF'
{
  "homeserver": "DISCOVERED_HOMESERVER_URL",
  "user_id": "USER_PROVIDED_USER_ID",
  "bot_prefix": "🤖"
}
EOF
chmod 600 ~/.config/matrix/config.json
```

### Step 5: Set up E2EE device (recommended)

> **⛔ Do not shortcut this step with a token you already have.**
>
> Copying an access token out of Element (or any other running client) looks like
> it works — the token is valid, calls succeed, messages send. It also hijacks
> that client's `device_id`. Encryption state is per device and lives in each
> client's local store, so the two now hold different session keys for the same
> identity: the client starts showing `[Unable to decrypt]` for its own messages
> and only recovers after a logout/login cycle.
>
> There is no warning at the moment you paste, and the symptom shows up in the
> other client, not here. The password below is used once and not stored; it buys
> a device that belongs to the skill alone.

**Three ways to provide the password:**

**Option A: Environment variable (recommended for agents)**
```bash
MATRIX_PASSWORD="USER_PASSWORD" uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py
```

**Option B: Interactive prompt (recommended for users)**
```bash
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py
# Script will securely prompt for password
```

**Option C: Command line argument (use with caution)**
```bash
set +H && uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py "USER_PASSWORD"
```

This creates a dedicated "Matrix Skill E2EE" device. The password is used once and not stored.

**Why environment variable?** Avoids shell escaping issues with special characters (`!`, `$`, etc.).

### Step 6: Add access token to config

After E2EE setup, copy the access token to enable non-E2EE scripts. The source is
the skill's own `credentials.json` — the command below reads it from there. Never
substitute a token from a client you use; the token in the config is the one most
likely to be copied around later.

```bash
ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.local/share/matrix-skill/store/credentials.json'))['access_token'])")

python3 -c "
import json
config_path = '$HOME/.config/matrix/config.json'
with open(config_path) as f:
    config = json.load(f)
config['access_token'] = '$ACCESS_TOKEN'
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print('Access token added to config')
"
```

### Step 7: Verify setup

```bash
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py --status
uv run skills/matrix-communication/scripts/matrix-rooms.py
```

### Step 8: Set up key backup recovery (optional)

To decrypt old messages sent before your device was created, restore keys from server-side backup:

```bash
# Check if backup exists
uv run skills/matrix-communication/scripts/matrix-key-backup.py --status

# Restore with recovery key (from Element → Settings → Security → "Show Recovery Key")
uv run skills/matrix-communication/scripts/matrix-key-backup.py --recovery-key "EsTj qRGp YB4C ..." --import-keys
```

**Note on non-interactive contexts:** All scripts use line buffering (`sys.stdout.reconfigure(line_buffering=True)`) to prevent output from hanging in piped/non-interactive environments like Claude Code.

## Troubleshooting

**A token you found somewhere is valid — that does not make it yours.**

When the configured token stops working, the tempting next step is the token
lying in a secrets file, an env var, or another tool's config. It authenticates,
`whoami` answers, calls succeed. It can still be the wrong credential, because a
token carries a `device_id` and that device may be a human's running client.

Before adopting any credential you did not create here:

```bash
HS=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/matrix/config.json')))['homeserver'])")
curl -s -H "Authorization: Bearer $TOKEN" "$HS/_matrix/client/v3/account/whoami"
curl -s -H "Authorization: Bearer $TOKEN" "$HS/_matrix/client/v3/devices" \
  | python3 -c "import json,sys;[print(d['device_id'], '-', d.get('display_name')) for d in json.load(sys.stdin)['devices']]"
```

If the `device_id` belongs to a device whose display name reads like a human
client — "Element Desktop: Windows", "Element X Android", "FluffyChat android" —
stop. That is someone's session, not an agent credential.

What happens if you use it anyway: the nio store creates its own olm account for
that device id, so one device now has two crypto identities. The client that
owns it starts failing to decrypt messages, including its own, and SAS
verification against the account's other devices fails with "expected key did
not match" — even after switching to a proper device, because the damage is on
the server-side device keys.

The only sanctioned path to an agent credential is `matrix-e2ee-setup.py`, which
logs in fresh and gets a device of its own.

**Recovery, if a foreign token was already used with the E2EE scripts:** treat
that device's crypto identity as spent. Log the agent device out
(`matrix-e2ee-setup.py --logout`, which touches only that device's files), set
up a fresh one, re-import the room keys, and verify again. The human client
whose device was hijacked needs a logout and a fresh login of its own; its local
session state cannot be repaired from this side.

**E2EE setup fails with "Invalid username or password":**

If your password contains special characters (`!`, `$`, `\`, etc.), bash may mangle them:

```bash
# WRONG - bash corrupts passwords with special characters
uv run .../matrix-e2ee-setup.py "MyPass!word"

# CORRECT - use environment variable (recommended)
MATRIX_PASSWORD="MyPass!word" uv run .../matrix-e2ee-setup.py

# CORRECT - use interactive prompt
uv run .../matrix-e2ee-setup.py
```

**E2EE setup fails with libolm error:**
```bash
# Debian/Ubuntu
sudo apt install libolm-dev

# Fedora
sudo dnf install libolm-devel
```

**macOS 26 (Tahoe) / Apple Clang 17 — `brew install libolm` does NOT help.**

`matrix-nio[e2e]` pulls in `python-olm`, which has **no macOS wheel** on PyPI and compiles a *bundled* copy of `libolm` from source, statically linked — it never uses the Homebrew library. That bundled build fails under Apple Clang 17 / CMake ≥ 3.30 (a C++ const-correctness hard error in `list.hh`, plus an obsolete `cmake_minimum_required(VERSION 3.4)`).

Workarounds, easiest first:

- Use the **non-E2EE scripts** (`matrix-send.py`, `matrix-rooms.py`, …) — they don't need `python-olm`.
- Run the **E2EE scripts from Linux or a Linux container**, where the pre-built wheel installs cleanly.
- Build `python-olm` on macOS with **GCC instead of Clang** (community-reported in https://github.com/matrix-nio/matrix-nio/issues/541; not verified by this project):

```bash
brew install gcc@12
export CC=/opt/homebrew/bin/gcc-12
export CXX=/opt/homebrew/bin/g++-12
export CMAKE_POLICY_VERSION_MINIMUM=3.5   # clears the CMake < 3.5 error
pip install 'matrix-nio[e2e]'             # GCC sidesteps the Clang 17 const error
```

**Upstream status:** `libolm` is archived and deprecated in favor of `vodozemac` (https://github.com/matrix-nio/matrix-nio/issues/518). The real fix — replacing olm with vodozemac in `matrix-nio` — is in progress as open PR https://github.com/matrix-nio/matrix-nio/pull/555; until it ships, macOS installs need one of the workarounds above. Related: https://github.com/matrix-nio/matrix-nio/issues/560 (macOS install) and https://github.com/matrix-nio/matrix-nio/issues/541 (CMake error). Tracking here: https://github.com/netresearch/matrix-skill/issues/43

**Non-E2EE scripts fail with "Config missing required fields: access_token":**

After E2EE setup, the access token is stored separately. Copy it to the main config using Step 6 above.

## Bash Quoting Notes

Bash history expansion treats `!` specially, which can corrupt messages and passwords.

```bash
# MOST RELIABLE - disable history expansion
set +H && uv run .../matrix-send-e2ee.py "#room:server" "Done!"

# Single quotes work for simple messages
uv run .../matrix-send-e2ee.py "#room:server" 'Done!'

# For passwords, use environment variable
MATRIX_PASSWORD="MyP@ss!word" uv run .../matrix-e2ee-setup.py
```
