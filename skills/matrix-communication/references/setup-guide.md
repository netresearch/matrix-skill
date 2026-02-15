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
- `libolm` - System library for Olm encryption (install via apt/dnf/brew)

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
  "bot_prefix": "bot-emoji"
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

# macOS
brew install libolm
```

**Non-E2EE scripts fail with "Config missing required fields: access_token":**

After E2EE setup, the access token is stored separately. Copy it to the main config using Step 6 above.

## Bash Quoting Notes

Bash history expansion treats `!` specially, which can corrupt messages and passwords.

```bash
# MOST RELIABLE - disable history expansion
set +H && uv run .../matrix-send.py "#room:server" "Done!"

# Single quotes work for simple messages
uv run .../matrix-send.py "#room:server" 'Done!'

# For passwords, use environment variable
MATRIX_PASSWORD="MyP@ss!word" uv run .../matrix-e2ee-setup.py
```
