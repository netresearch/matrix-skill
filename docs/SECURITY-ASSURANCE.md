<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Security assurance case

This document states what a user can expect from this repository in terms of security, and argues why that expectation holds. Every claim names the file that implements it. Reporting a vulnerability: see the [security policy](https://github.com/netresearch/.github/blob/main/SECURITY.md). Components and data flows: [ARCHITECTURE.md](ARCHITECTURE.md). Scanner findings reviewed earlier: [SECURITY-AUDIT.md](../SECURITY-AUDIT.md).

Paths below are relative to `skills/matrix-communication/scripts/` (`C/`) and `skills/matrix-administration/scripts/` (`A/`).

## What the repository ships

| Part | Files | Runs where |
| --- | --- | --- |
| Skill instructions for an AI agent | `skills/*/SKILL.md`, `skills/*/references/*.md`, `commands/work-update.md` | Read by the agent; not executed. The agent runs the scripts they describe with the user's privileges. |
| Chat scripts (Client-Server API) | `C/matrix-*.py`, `C/_lib/` | On the user's machine, via `uv run` (`matrix-doctor.py` via `python3`). The `*-e2ee.py` scripts, `matrix-e2ee-setup.py`, `matrix-e2ee-verify.py`, `matrix-watchd.py`, `matrix-fetch-keys.py` and `matrix-key-backup.py` use `matrix-nio[e2e]<0.26`; the rest is stdlib only. |
| Watch daemon | `C/matrix-watchd.py`, reader `C/matrix-watch.py` | A background process of the user that syncs, decrypts and appends events to per-room logs, and serves send/react/edit/redact on a Unix socket. |
| Homeserver administration scripts | `A/synapse-*.py`, `A/_lib/` | On the user's machine, stdlib only, against the Synapse Admin API with a server-admin token. |
| Announcement guidance | `skills/matrix-announcement/` | Text and HTML templates; nothing is executed. |
| Tests | `C/_lib/test_*.py`, `C/test_matrix_doctor.py`, `A/_lib/test_config.py`, `A/test_migrate_room.py` | In CI (`.github/workflows/tests.yml`) and on contributors' machines. No test contacts a homeserver. |

The repository ships no server component, no container image and no compiled code.

## Security requirements

1. Every request that carries a token is addressed to the configured homeserver over `http` or `https`, and no script prints a token.
2. The skill does not reuse another client's device: E2EE runs on a device of its own, whose credentials file is set to mode `0600`.
3. Commands that open the stored device's E2EE store do so one process at a time, so they cannot corrupt it by running concurrently.
4. A token can be kept outside `config.json` and rotated without editing it.
5. User deactivation and room migration (which enables encryption, a one-way change) do not run without an explicit confirmation.
6. The daemon's command socket is set to mode `0600`, so only the account that runs the daemon can connect to it.
7. Nothing committed to this repository contains a secret, and a release can be verified against the build that produced it.

## Actors and trust boundaries

- **User and agent.** The agent reads the skill files and runs the scripts with the user's operating-system account. It decides what to send; the scripts do not restrict which rooms or users it addresses.
- **The user's configuration.** `~/.config/matrix/config.json` (`$XDG_CONFIG_HOME` respected, `C/_lib/config.py`, `A/_lib/config.py`) is trusted: it names the homeserver the tokens are sent to. Environment variables and token files named in it are trusted the same way.
- **The homeserver.** Receives the tokens and is trusted with them. Its responses are parsed as JSON (`C/_lib/http.py`, `A/_lib/admin_http.py`) and by `matrix-nio`.
- **Other room members and their messages.** Message bodies arriving through `matrix-read*.py`, `matrix-watchd.py` and `synapse-search.py` are data written by other people. For an agent they are untrusted input; `skills/matrix-communication/references/agent-governance.md` sets the rule that only the principal governs the agent, not anyone in a room.
- **Other processes of the same user.** Share the operating-system account; they can read the user's files and connect to the daemon socket. The skill does not defend against them.
- **Contributors and CI.** Changes reach `main` through pull requests checked by `.github/workflows/`. Workflows start from `permissions: {}` and grant each job only the scopes its reusable workflow needs.

## Where secrets are read, stored and sent

| Secret | Read from | Stored by the skill | Sent to |
| --- | --- | --- | --- |
| Access token (non-E2EE scripts; the E2EE scripts fall back to it when `credentials.json` is missing) | `MATRIX_ACCESS_TOKEN`, else the file named by `access_token_file`, else `access_token` in `config.json` (`resolve_tokens` in `C/_lib/config.py`) | Nowhere; it stays where the user put it | `Authorization: Bearer` header to `<homeserver>/_matrix/client/v3/...` (`C/_lib/http.py`) |
| Admin token | `MATRIX_ADMIN_TOKEN` / `admin_token_file` / `admin_token`, falling back to the access token sources (`A/_lib/config.py`) | Nowhere | `Authorization: Bearer` header to `<homeserver>/_synapse/admin/...` and `/_matrix/client/v3/...` (`A/_lib/admin_http.py`) |
| Account password | Interactive prompt without echo (`getpass`), `MATRIX_PASSWORD`, or a positional argument (`C/matrix-e2ee-setup.py`) | Not stored; used once for the login that creates the device | The homeserver's login endpoint, through `matrix-nio` |
| E2EE device access token | Returned by that login | `credentials.json` in `$XDG_DATA_HOME/matrix-skill/store/`, mode `0600` (`save_credentials` in `C/_lib/e2ee.py`) | The homeserver, through `matrix-nio` and `C/_lib/http.py` |
| Olm/Megolm keys | Created and received by `matrix-nio` | The `matrix-nio` store in the same directory | Room keys go to the user's other devices and room members as the Matrix protocol requires; `matrix-nio` handles this |
| Key backup recovery key or passphrase | `--recovery-key` / `--passphrase` of `C/matrix-key-backup.py` | Not stored | Not sent; used locally to decrypt the backup key |
| Decrypted backup key | Derived from the recovery key | `backup_key.json` in the store directory, mode `0600` (`C/matrix-key-backup.py`), reused only after it is checked against the server's current backup | Not sent |

`matrix-doctor.py` verifies tokens with `GET /account/whoami` and reports the result by label (`admin_token`, `access_token`, `E2EE credential (<device>)`), never by value. A token file that cannot be read produces an error naming the file, not its content (`TokenSourceError` in both `_lib/config.py`; tested in `C/_lib/test_config.py`).

## Threats and countermeasures

| Threat | Countermeasure | Evidence |
| --- | --- | --- |
| A configured homeserver value such as `file:///etc/passwd` turns a request into a local file read (CWE-73) | The standard-library request helpers check the URL against an `http`/`https` allow-list before they open it; `matrix-nio` and `aiohttp` accept only HTTP URLs themselves | `_require_http_scheme` in `C/_lib/http.py` and `A/_lib/admin_http.py`; `matrix-doctor.py` routes its check through the same helper |
| The agent drives an existing client's device and breaks its decryption | `matrix-e2ee-setup.py` logs in with the password and creates a device of its own; the doctor fails when the stored token belongs to a different device than `credentials.json` names | `C/matrix-e2ee-setup.py`; `check_e2ee_setup` in `C/matrix-doctor.py`; `C/test_matrix_doctor.py` |
| Two processes open the E2EE store at once and corrupt it silently | Every command that restores the stored device (`restore_login_checked`, used by the `*-e2ee.py` scripts, `matrix-fetch-keys.py`, `matrix-key-backup.py` and `matrix-watchd.py`) takes an exclusive `flock` and holds it until exit; a second process waits, then refuses and names the holder | `store_lock`, `restore_login_checked` in `C/_lib/e2ee.py`; `C/_lib/test_e2ee.py` |
| Logging out one device deletes the keys of every other device in the shared store | `delete_credentials` removes only the files named `<user>_<device>.*` of the device being logged out; `--purge-all` is required for the whole store | `C/_lib/e2ee.py`; `C/_lib/test_e2ee.py` |
| A stored backup key from an older backup is used against a new one | The stored key is used only when it matches the server's current backup version and public key | `load_stored_backup_key` in `C/matrix-key-backup.py` |
| Another local user sends messages as this user through the daemon | The socket is set to mode `0600` right after it is created, in `$XDG_RUNTIME_DIR/matrix-skill/` (or `~/.local/share/matrix-skill/`) | `C/matrix-watchd.py`, `socket_path` in `C/_lib/daemon_client.py` |
| A malformed socket request stops the daemon | Requests are one JSON line each; unknown operations and exceptions return an error object instead of ending the process | `handle_client`, `dispatch` in `C/matrix-watchd.py` |
| A room id becomes a path outside the log directory (CWE-22) | Log file names keep only `[A-Za-z0-9._-]` of the room id; everything else becomes `_` | `C/_lib/roomlog.py`; `C/_lib/test_roomlog.py` |
| An operator deactivates a user or encrypts a room by accident | `synapse-deactivate-user.py` and `synapse-migrate-room.py` print the plan and ask; without a terminal they refuse unless `--yes` is given | `A/synapse-deactivate-user.py`, `A/synapse-migrate-room.py`; `A/test_migrate_room.py` |
| A token kept in `config.json` has to be rotated or shared with the rest of the configuration | Tokens can come from the environment or a separate file; precedence environment, file, inline value | `resolve_tokens` in both `_lib/config.py`; `C/_lib/test_config.py`, `A/_lib/test_config.py` |
| A command runs through a shell with attacker-influenced text (CWE-78) | `subprocess` is called with argument lists and without `shell=True` (`pip`/`uv` in the doctor, `dot` in the graph script, `matrix-watchd.py --start` launching itself in the background) | `C/matrix-doctor.py`, `A/synapse-graph.py`, `C/matrix-watchd.py` |
| A newer `matrix-nio` writes a store the pinned version cannot read, or breaks SAS verification with Element | Every script that imports `nio` pins `matrix-nio[e2e]<0.26` in its PEP 723 block; the store error is explained instead of surfacing as `BAD_ACCOUNT_KEY` | PEP 723 blocks in `C/*.py`; `explain_store_error` in `C/_lib/e2ee.py` |
| A secret is committed | Betterleaks scans every push to `main` and every pull request to `main` | `.github/workflows/security.yml` |
| Insecure code or workflow patterns | Opengrep SAST fails on findings at the threshold the organisation's [static analysis rule](https://github.com/netresearch/.github/blob/main/SECURITY.md#static-analysis-sast) sets; zizmor analyses the workflows; ruff and ShellCheck run in Skill Validation | `.github/workflows/security.yml`, `.github/workflows/lint.yml` |
| A released archive is tampered with | The release workflow publishes a Cosign-signed `SHA256SUMS.txt` and build-provenance attestations | `.github/workflows/release.yml` (calls the skill-repo-skill release reusable) |

Which of these checks must pass before a pull request can merge is set in the branch protection of `main`, not in this repository.

## Secure design principles applied

- **Least privilege:** the chat scripts use a device and token of their own, separate from the user's clients; the admin token is needed only by `synapse-*` scripts; workflows start from `permissions: {}`.
- **Fail-safe defaults:** user deactivation and room migration refuse without a terminal or `--yes`; a check the doctor cannot complete reports "not verified", never OK (`C/matrix-doctor.py`); logout without credentials removes nothing (`delete_credentials`).
- **Complete mediation of the store:** every command that restores the stored device goes through `restore_login_checked`, which takes the lock first.
- **Economy of mechanism:** the non-E2EE and admin scripts use only the Python standard library; the E2EE scripts add `matrix-nio`, and `matrix-key-backup.py` also `cryptography` and `aiohttp`.
- **Separation of secrets from configuration:** tokens may live in the environment or a token file (`resolve_tokens`); the E2EE token lives in its own file, not in `config.json`.

## What a user cannot expect

- The configured homeserver is trusted. The scripts accept `http://` as well as `https://`; with `http://` the token travels unencrypted. TLS certificates are verified against the default trust store of `urllib` and `aiohttp`; no certificate is pinned.
- The skill does not check the permissions of `config.json` or of a token file; protecting them is the user's job.
- The scripts act with the user's operating-system account. Any process of that account can read its tokens and store and use the daemon socket.
- Messages read from rooms are untrusted text. The skill cannot stop an agent from following instructions contained in them; that is a property of the agent (see `SECURITY-AUDIT.md`, W011, and `skills/matrix-communication/references/agent-governance.md`).
- Only deactivation and room migration ask for confirmation. `synapse-make-admin.py` (a permanent power level 100), `synapse-join-room.py`, `synapse-add-to-space.py`, `matrix-power-level.py`, `matrix-redact.py` and `matrix-e2ee-setup.py --logout --purge-all` act as soon as they are called.
- `matrix-e2ee-setup.py` does not take the store lock. Its `--logout` removes the device's store files even while `matrix-watchd.py` has them open; stop the daemon first.
- `synapse-search.py` sees only unencrypted events; an empty result does not mean there were no messages.
- The Python dependencies are declared inline in each script, not in a manifest GitHub's dependency graph reads, so dependency review does not cover `matrix-nio`. `matrix-doctor.py --install` installs `matrix-nio[e2e]<0.26` from the package index without hash pinning.
- `allowed-tools` in a `SKILL.md` pre-approves tools for the agent; it does not remove any tool the agent already has and is not a sandbox.
- Security fixes follow the supported-versions rules of the organisation's security policy; older releases may not receive them.
