# Matrix Skill Setup Guide

Complete setup walkthrough for the Matrix communication skill.

## Prerequisites

Before using E2EE features, check dependencies:

```bash
# Run health check (checks all dependencies)
python3 skills/matrix-communication/scripts/matrix-doctor.py

# Auto-install missing dependencies
python3 skills/matrix-communication/scripts/matrix-doctor.py --install
```

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

After E2EE setup, copy the access token to enable non-E2EE scripts:

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
