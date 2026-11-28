<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Matrix Skill Setup Guide

Complete setup walkthrough for the Matrix communication skill.

## Prerequisites

Before using E2EE features, check dependencies:

```bash
# Run health check (checks all dependencies)
uv run skills/matrix-communication/scripts/matrix-doctor.py

# Auto-install missing dependencies
uv run skills/matrix-communication/scripts/matrix-doctor.py --install

# Skip the homeserver call (air-gapped / CI): the token row then reads
# 'not verified' instead of OK, and the summary says so
uv run skills/matrix-communication/scripts/matrix-doctor.py --offline
```

The `token` row asks the homeserver (`GET /_matrix/client/v3/account/whoami`)
whether matrix-administration's `admin_token` actually works, because a revoked
or expired token leaves the config file perfectly well-formed. The skill's own
device is checked the same way in the `e2ee_setup` row. It has three outcomes:

| row | meaning |
| --- | --- |
| `[OK] token` | the homeserver accepted it and it belongs to the configured `user_id` |
| `[FAIL] token` | the homeserver rejected it (HTTP 401 `M_UNKNOWN_TOKEN`) — log in again and replace it |
| `[??] token` | nothing was verified: no admin token in the config (normal: the scripts use matrix-e2ee-cli's session), `--offline`, or the homeserver was unreachable |

`[??]` is deliberately not `OK`: the summary then reads "Checks passed, except
token — could not be verified" rather than "All checks passed", so a passing
doctor never implies a working credential.

**Required:** the [matrix-e2ee-cli](https://github.com/netresearch/matrix-e2ee-cli)
binary for this platform (Linux and macOS on x86_64 and arm64, Windows on
x86_64). The scripts download the release pinned in
`scripts/_lib/cli_release.json` on first use and check its SHA-256;
`matrix-doctor.py --install` does that in advance. `MATRIX_E2EE_CLI=/path` uses
a binary of your own instead. No native library and no Python package is
needed.

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

### Step 5: Set up E2EE device (required: every script uses it)

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

**Two ways to provide the password:**

**Option A: Environment variable (recommended for agents)**
```bash
MATRIX_PASSWORD="USER_PASSWORD" uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py
```

**Option B: Interactive prompt (recommended for users)**
```bash
uv run skills/matrix-communication/scripts/matrix-e2ee-setup.py
# Script will securely prompt for password
```

A password given as a command-line argument is refused: every local user can
read it in the process list while setup runs. `--allow-secret-argument`
accepts it anyway, for automation that can use neither option above.

This creates a dedicated device named "Matrix Skill E2EE (Rust)". The password is used once and not stored.

A machine that ran version 4 or older of this skill keeps its device: the first
E2EE command takes the matrix-nio device over instead of creating a new one
(`e2ee-guide.md`, "Moving from matrix-nio").

Run with a session already in place, `matrix-e2ee-setup.py` only shows its
state. `--force` replaces a dead or foreign device with a new one; the old
device stays on the server until you remove it in Element. On a machine still
on matrix-nio the takeover runs first, so `--force` then replaces the device
just taken over: use it only when that device is dead or foreign too.

**Why environment variable?** Avoids shell escaping issues with special characters (`!`, `$`, etc.).

### Step 6: No access token in the config

Nothing to copy: every script logs in with the matrix-e2ee-cli session that
step 5 created. If `config.json` still carries an `access_token` or
`access_token_file` from version 5 (or `MATRIX_ACCESS_TOKEN` is exported),
remove it; no script reads it, and `matrix-doctor.py` warns while it is there.
When it is the token of the skill's own device, the doctor says so, and
removing it logs nothing out.

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

# Restore with recovery key (from Element → Settings → Security → "Show Recovery Key");
# the script prompts for it, or reads MATRIX_RECOVERY_KEY
uv run skills/matrix-communication/scripts/matrix-key-backup.py --import-keys
```

## Element labels for instructions to people

When you write step-by-step instructions for people who use Element (sign out, change the homeserver, set up recovery), take every menu item and button label from the client's translation files at a release tag, never from memory, and name that version in the instructions. Labels change between releases: "Sign out" in Element Web v1.11.100 is "Remove this device" in v1.12.35.

Use the tag of the version the readers actually run — ask, or read it in the client under Settings → Help & About. Take the latest release only when that is what they run (a self-hosted Element Web you just upgraded, desktop or mobile apps that update themselves):

```bash
gh api repos/element-hq/element-web/releases/latest --jq .tag_name
gh api repos/element-hq/element-x-android/releases/latest --jq .tag_name
```

| Client | File at the release tag |
|---|---|
| Element Web and Desktop, v1.12.12 and later | `apps/web/src/i18n/strings/<locale>.json` in `element-hq/element-web`; keys such as `action.edit`, `common.homeserver`, `auth.server_picker_custom` |
| Element Web and Desktop, up to v1.12.11 | `src/i18n/strings/<locale>.json` (the path before the monorepo move; 404 from v1.12.12 on) |
| Element X Android | `features/<feature>/impl/src/main/res/values-<lang>/translations.xml` and `libraries/ui-strings/src/main/res/values-<lang>/translations.xml` in `element-hq/element-x-android`; English, the base language, is `values/localazy.xml` in the same directories |

The string file gives the words, not the place: find the component that renders a key to say which screen or tab holds the button. In Element Web's source a key is written with `|`, not `.` (`_t("action|sign_out")` for the JSON path `action.sign_out`). `gh search code` searches only the default branch, so use it to find candidate files, then confirm the file at the chosen tag; the `apps/web/` prefix is missing before v1.12.12:

```bash
gh search code '"action|sign_out"' --repo element-hq/element-web --json path --jq '.[].path'
gh api "repos/element-hq/element-web/contents/<path>?ref=<tag>" --jq .content | base64 -d | grep -n 'action|sign_out'
```

Two labels that read differently from older instructions (Element Web v1.12.35, Element X Android v26.11.0, English / German):

- Signing out is "Remove this device" / „Dieses Gerät entfernen“ (key `action.sign_out`; Element X `action_signout`), not "Sign out".
- The homeserver is the "Account provider" / „Kontoanbieter“ (`common.homeserver`). Changing it: "Edit" next to it, then "Other account provider" on Web; "Sign in manually", then "Change account provider" / „Kontoanbieter wechseln“ in Element X.

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

What happens if you use it anyway: the skill's store creates its own olm account for
that device id, so one device now has two crypto identities. The client that
owns it starts failing to decrypt messages, including its own, and SAS
verification against the account's other devices fails with "expected key did
not match" — even after switching to a proper device, because the damage is on
the server-side device keys.

The only sanctioned path to an agent credential is `matrix-e2ee-setup.py`, which
logs in fresh and gets a device of its own.

**Recovery, if a foreign token was already used with the E2EE scripts:** treat
that device's crypto identity as spent. Log the agent device out
(`matrix-e2ee-cli.py logout`, which ends that device on the server and deletes
the local session and store), set up a fresh one, re-import the room keys, and verify again. The human client
whose device was hijacked needs a logout and a fresh login of its own; its local
session state cannot be repaired from this side.

**E2EE setup fails with "Invalid username or password":**

If your password contains special characters (`!`, `$`, `\`, etc.), bash may mangle them:

```bash
# WRONG - bash corrupts passwords with special characters, and the
# argument is refused anyway (visible in the process list)
uv run .../matrix-e2ee-setup.py "MyPass!word"

# CORRECT - use environment variable (recommended)
MATRIX_PASSWORD="MyPass!word" uv run .../matrix-e2ee-setup.py

# CORRECT - use interactive prompt
uv run .../matrix-e2ee-setup.py
```

**E2EE scripts fail with `no matrix-e2ee-cli release for …`:** there is no release
binary for this platform. Build matrix-e2ee-cli yourself (`cargo build --release`)
and set `MATRIX_E2EE_CLI` to the binary.

**`matrix-doctor.py` warns that `access_token` is no longer used:**

Remove it from `config.json` (Step 6 above).

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
