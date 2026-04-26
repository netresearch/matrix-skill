# Safety guide

These scripts hold a **Synapse server-admin token**. A bad command is visible homeserver-wide and a few are not reversible. Read this once before running anything new.

## Pre-flight checklist

Before any state-changing command:

1. **Confirm the homeserver URL** in `~/.config/matrix/config.json` — the wrong host with the right script wipes the wrong server.
2. **Confirm the user/room/space ID** you typed. Matrix IDs are similar; copy/paste them and read them back.
3. **Run any read-only script first** to verify the target exists:
   - `python3 …/synapse-user-rooms.py '@user:server'`
   - `python3 …/synapse-room-member-flow.py '!room:server'`
4. For destructive operations, **dry-run by hand**: print the planned action to stdout (`echo`, `python3 -c 'print(…)'`) and ask the operator to confirm before invoking the script.

## Per-script risks

### `synapse-deactivate-user.py`

- Calls `POST /_synapse/admin/v1/deactivate/{user_id}`.
- The user **cannot log in again**, all access tokens are revoked, the user is **left from every joined room**.
- With `--erase`, message bodies are also redacted (GDPR right-to-erasure).
- Not reversible without a database operation by a homeserver operator.
- The script prints the user's profile + joined rooms before and after, and refuses to run non-interactively without `--yes`.

### `synapse-migrate-room.py`

The hardening pipeline is **partially irreversible**:

| Step | Reversible? |
|------|-------------|
| Add to space | yes — remove the `m.space.child` event |
| Force-join the caller | yes — leave the room |
| Promote to PL 100 | yes — restored at the end of the pipeline |
| Switch `public` → `restricted` | yes — change `m.room.join_rules` back |
| Enable encryption | **no** — Megolm cannot be turned off |

The room version must be > 9 for `restricted` joins; otherwise the script prints a red ❌ for that step. Switching to `restricted` removes discoverability for users not in the parent space.

### `synapse-make-admin.py` / `synapse-join-room.py`

- Only works while *some* existing admin is still in the room (Synapse refuses otherwise).
- If the original owner has already left, the room is **unrecoverable** through this tool — Synapse explicitly forbids re-creating admin from outside.

### `synapse-search.py`

- Read-only on the API. Risk is **misinterpretation**: only **unencrypted** messages are indexed. An empty result on an E2EE room means "search saw nothing", not "the user did not say anything". Use Element / a real client when you need plaintext from an encrypted room.

### `synapse-fetch-rooms.py`

- Read-only, but the resulting `rooms.json` contains user IDs, room names, power levels and join policies for **every** indexed room.
- **Never commit it** — the skill's `.gitignore` does not cover the working directory the script is run in.
- Treat the file the same as the admin token.

## Token hygiene

- The admin token is equivalent to root on the homeserver. Store it only in `~/.config/matrix/config.json` (or a secret manager that writes that file at startup).
- Rotate it after onboarding/offboarding any user who had file-system access to a host that ran these scripts.
- If you publish a Docker image (e.g. the graph dashboard from `room-graph-pipeline.md`), pass the token via `--secret`, never via `ENV` or build args.
