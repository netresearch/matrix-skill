<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Security assurance case

This document states what a user can expect from this repository in terms of security, and argues why that expectation holds. Every claim names the file that implements it. Reporting a vulnerability: see the [security policy](https://github.com/netresearch/.github/blob/main/SECURITY.md). Components and data flows: [ARCHITECTURE.md](ARCHITECTURE.md). Scanner findings reviewed earlier: [SECURITY-AUDIT.md](../SECURITY-AUDIT.md).

Paths below are relative to `skills/matrix-communication/scripts/` (`C/`) and `skills/matrix-administration/scripts/` (`A/`).

## What the repository ships

| Part | Files | Runs where |
| --- | --- | --- |
| Skill instructions for an AI agent | `skills/*/SKILL.md`, `skills/*/references/*.md`, `commands/work-update.md` | Read by the agent; not executed. The agent runs the scripts they describe with the user's privileges. |
| Chat scripts (Client-Server API) | `C/matrix-*.py`, `C/_lib/` | On the user's machine, via `uv run`, stdlib only. Every `matrix-*.py` script except `matrix-doctor.py` translates its flags and runs the [matrix-e2ee-cli](https://github.com/netresearch/matrix-e2ee-cli) binary, which does all end-to-end encryption and every request to the homeserver; `matrix-doctor.py` asks `/account/whoami` itself (`C/_lib/http.py`). |
| matrix-e2ee-cli binary | Downloaded from that repository's GitHub release into `<data dir>/matrix-skill/cli/<version>/` (`C/_lib/cli.py`) | On the user's machine, as a child process of the wrappers. Its own security case is that repository's; this document covers how the skill obtains and calls it. |
| Watch daemon | `matrix-e2ee-cli watch-daemon`, started by `C/matrix-watchd.py`; reader `matrix-e2ee-cli watch` through `C/matrix-watch.py` | A background process of the user that syncs, decrypts and appends events to per-room logs, and serves the CLI's send/react/edit/redact on a Unix socket. |
| Homeserver administration scripts | `A/synapse-*.py`, `A/_lib/` | On the user's machine, stdlib only, against the Synapse Admin API with a server-admin token. |
| Announcement guidance | `skills/matrix-announcement/` | Text and HTML templates; nothing is executed. |
| Tests | `C/_lib/test_*.py`, `C/test_matrix_doctor.py`, `C/test_e2ee_wrappers.py`, `A/_lib/test_*.py`, `A/test_migrate_room.py`, `A/test_synapse_graph.py` | In CI (`.github/workflows/tests.yml`) and on contributors' machines. No test contacts a homeserver. |

The repository ships no server component, no container image and no compiled code; the E2EE binary is the matrix-e2ee-cli release whose SHA-256 `C/_lib/cli_release.json` pins.

## Security requirements

1. Every request that carries a token is addressed to the configured homeserver over `http` or `https`, a redirect to another origin does not carry it, and no script prints a token.
2. The skill does not reuse another client's device: E2EE runs on a device of its own, whose session file matrix-e2ee-cli creates with mode `0600` in a directory only its owner can enter.
3. Commands that open the stored device's E2EE store do so one process at a time, so they cannot corrupt it by running concurrently.
4. A token can be kept outside `config.json` and rotated without editing it.
5. User deactivation and room migration (which enables encryption, a one-way change) do not run without an explicit confirmation.
6. The daemon's command socket lives in an owner-only directory and is set to mode `0600`, so only the account that runs the daemon can connect to it.
7. Nothing committed to this repository contains a secret, and a release can be verified against the build that produced it.
8. Decrypted messages, key material and credentials on disk are readable by the owning account only.
9. Room keys are shared with verified devices only, unless the user opts in for one command (`--trust-unverified-devices`), and verification is answered only for the account's own devices.
10. Secrets are not taken from the command line unless the user opts in (`--allow-secret-argument`), and never reach the E2EE binary on its command line.
11. The E2EE binary that runs is the release whose SHA-256 the skill pins, or one the user names explicitly (`MATRIX_E2EE_CLI`).
12. Moving to matrix-e2ee-cli does not lose the device of a matrix-nio store: it is taken over after a backup copy, or the command does not run.

## Actors and trust boundaries

- **User and agent.** The agent reads the skill files and runs the scripts with the user's operating-system account. It decides what to send; the scripts do not restrict which rooms or users it addresses.
- **The user's configuration.** `~/.config/matrix/config.json` (`$XDG_CONFIG_HOME` respected, `C/_lib/config.py`, `A/_lib/config.py`) is trusted: it names the homeserver the tokens are sent to. Environment variables and token files named in it are trusted the same way.
- **The homeserver.** Receives the tokens and is trusted with them. Its responses are parsed as JSON (`C/_lib/http.py`, `A/_lib/admin_http.py`) and by matrix-e2ee-cli.
- **Other room members and their messages.** Message bodies arriving through `matrix-read*.py`, `matrix-watch.py` and `synapse-search.py` are data written by other people. For an agent they are untrusted input; `skills/matrix-communication/references/agent-governance.md` sets the rule that only the principal governs the agent, not anyone in a room.
- **Other processes of the same user.** Share the operating-system account; they can read the user's files and connect to the daemon socket. The skill does not defend against them.
- **Contributors and CI.** Changes reach `main` through pull requests checked by `.github/workflows/`. Workflows start from `permissions: {}` and grant each job only the scopes its reusable workflow needs.

## Where secrets are read, stored and sent

| Secret | Read from | Stored by the skill | Sent to |
| --- | --- | --- | --- |
| Admin token | `MATRIX_ADMIN_TOKEN` / `admin_token_file` / `admin_token`, falling back to the E2EE device access token in matrix-e2ee-cli's `session.json` (`A/_lib/config.py`); `access_token`, `access_token_file` and `MATRIX_ACCESS_TOKEN` are not read | Nowhere | `Authorization: Bearer` header to `<homeserver>/_synapse/admin/...` and `/_matrix/client/v3/...` (`A/_lib/admin_http.py`); the session's token to the homeserver recorded in `session.json` |
| Account password | Interactive prompt of matrix-e2ee-cli or `MATRIX_PASSWORD`; a positional argument of `C/matrix-e2ee-setup.py` only with `--allow-secret-argument`, passed on as `MATRIX_PASSWORD` in the child's environment (`secret_env` in `C/_lib/wrapper.py`) | Not stored; used once for the login that creates the device | The homeserver's login endpoint, through matrix-e2ee-cli |
| E2EE device access token | Returned by that login, or taken over from a matrix-nio store | matrix-e2ee-cli's `session.json` (mode `0600`, directory `0700`; that repository's `src/session.rs`). The takeover leaves the old `credentials.json` in `matrix-skill/store/` and copies it into `matrix-skill/store.backup-<time>/` (directories `0700`, files `0600`; `backup_store` in `C/_lib/cutover.py`) | The homeserver recorded in `session.json`, through matrix-e2ee-cli, through `C/_lib/http.py` for the doctor's check, and through `A/_lib/admin_http.py` when no admin token is set |
| Olm/Megolm keys | Created and received by matrix-e2ee-cli | matrix-e2ee-cli's store, encrypted with the passphrase in `session.json`. The old matrix-nio store and its backup copy keep the keys of version 4 (with a `backup_key.json` when version 4 wrote one) until the user deletes them | Room keys go to verified devices of room members; unverified ones only with `--trust-unverified-devices`, for that one message (matrix-e2ee-cli `send`, `edit`) |
| Key backup recovery key or passphrase | Prompt of matrix-e2ee-cli or `MATRIX_RECOVERY_KEY` / `MATRIX_RECOVERY_PASSPHRASE`; a value on the command line of `C/matrix-key-backup.py` only with `--allow-secret-argument`, passed on in the environment (`secret_env` in `C/_lib/wrapper.py`) | Not stored by this repository | Not sent; matrix-e2ee-cli uses it to open the secret storage |

`matrix-doctor.py` verifies tokens with `GET /account/whoami` and reports the result by label (`admin_token`, `E2EE credential (<device>)`), never by value. An `access_token` left in `config.json` is never sent; the doctor warns that it is unused and names its device only when it equals the token in `session.json`. A token file that cannot be read produces an error naming the file, not its content (`TokenSourceError` in both `_lib/config.py`; tested in `C/_lib/test_config.py`).

## Threats and countermeasures

| Threat | Countermeasure | Evidence |
| --- | --- | --- |
| A configured homeserver value such as `file:///etc/passwd` turns a request into a local file read (CWE-73) | The standard-library request helpers check the URL against an `http`/`https` allow-list before they open it; the E2EE requests are matrix-e2ee-cli's | `_require_http_scheme` in `C/_lib/http.py` and `A/_lib/admin_http.py`; `matrix-doctor.py` routes its check through the same helper |
| The agent drives an existing client's device and breaks its decryption | `matrix-e2ee-setup.py` logs in with the password and creates a device of its own; the doctor fails when the stored token belongs to a different device than matrix-e2ee-cli's `session.json` names | `C/matrix-e2ee-setup.py`; `check_e2ee_setup` in `C/matrix-doctor.py`; `C/test_matrix_doctor.py` |
| Two processes open the E2EE store at once and corrupt it silently | matrix-e2ee-cli locks its data directory for every command that opens its store. The takeover takes the matrix-nio store's `.daemon.lock` without waiting and stops while an older process holds it, before it copies anything | `store_lock` in `C/_lib/cutover.py`; `C/_lib/test_cutover.py` |
| A wrapper flag that only deleted local files now ends the device on the server | `matrix-e2ee-setup.py --logout` and `--purge-all` are refused, never mapped to `matrix-e2ee-cli logout` | `C/matrix-e2ee-setup.py`; `C/test_e2ee_wrappers.py` |
| The move to matrix-e2ee-cli loses the matrix-nio device or its keys | Before the first CLI command, and before an explicit `matrix-e2ee-cli.py migrate-nio`, the store is copied to an owner-only backup; `migrate-nio` only reads the store; a failure stops the command; the takeover runs under one lock and rechecks its marker inside it, so concurrent commands take over once; a marker file prevents a second takeover after a later logout | `C/_lib/cutover.py`, `C/_lib/wrapper.py`; `C/_lib/test_cutover.py`, `C/test_e2ee_wrappers.py` |
| The takeover's report reaches a caller that parses stdout (`Event ID: …`, JSON) | Everything the takeover prints goes to stderr | `migrate` in `C/_lib/cutover.py`; `C/test_e2ee_wrappers.py` |
| Another local user sends messages as this user through the daemon | The daemon's socket is `daemon.sock` in matrix-e2ee-cli's owner-only (`0700`) data directory, set to mode `0600` | matrix-e2ee-cli `src/commands/watch_daemon.rs`, `src/session.rs` |
| Another local user reads decrypted messages, credentials or key material (CWE-276) | matrix-e2ee-cli keeps its data directory `0700` and its session file `0600`; the takeover backup is made `0700`/`0600` | matrix-e2ee-cli `src/session.rs`; `backup_store` in `C/_lib/cutover.py`, `C/_lib/test_cutover.py` |
| A redirect from the homeserver carries the access token to another host (CWE-200) | The request helpers drop `Authorization` when a redirect leaves the origin (scheme, host, port) | `_SameOriginAuthRedirectHandler` in `C/_lib/http.py` and `A/_lib/admin_http.py`; `C/_lib/test_http.py`, `A/_lib/test_admin_http.py` |
| A device nobody verified receives room keys (CWE-295) | matrix-e2ee-cli's send and edit refuse in an encrypted room with unverified devices unless `--trust-unverified-devices` is given for that one message; reactions (`matrix-react.py`, matrix-e2ee-cli `react`) are sent unencrypted, so no key is shared | matrix-e2ee-cli `src/commands/send.rs` |
| Another user's device is marked verified by a SAS exchange only that user checked | matrix-e2ee-cli verifies devices of the account's own user only; the wrapper refuses `--accept-from`. With `--hand-over` the emoji are confirmed only by `verify --confirm TOKEN` for that comparison | matrix-e2ee-cli `src/commands/verify.rs`, `verify_handover.rs`; `C/matrix-e2ee-verify.py`, `C/test_e2ee_wrappers.py` |
| A secret given as an argument is read by another local user from the process list (CWE-214) | Password, recovery key and passphrase come from the environment or a prompt; an argument value is refused without `--allow-secret-argument`, and an accepted one reaches the CLI in its environment, not its argv | `secret_env` in `C/_lib/wrapper.py`; `C/test_e2ee_wrappers.py` |
| A different or tampered E2EE binary runs | The SHA-256 pinned in `C/_lib/cli_release.json` is checked before every run; a download goes to a temporary file and is moved into place only when its hash matches, else deleted unrun; the pin is part of this repository, not a SHA256SUMS fetched beside the binary | `C/_lib/cli.py`, `Build/Scripts/pin-cli-release.py`; `C/_lib/test_cli.py` |
| Message text becomes markup in the formatted body (CWE-79) | `markdown_to_html` escapes the text before it generates tags; links are made for `http`, `https`, `mailto` and `matrix` URLs only | `C/_lib/formatting.py`; `C/_lib/test_formatting.py` |
| A room or space name ends its DOT string and adds graph attributes (CWE-74) | Every room-supplied value in a node label is escaped | `node_label` in `A/synapse-graph.py`; `A/test_synapse_graph.py` |
| A room, user or event id changes which API path a request reaches | Ids are URL-encoded as one path segment; the chat scripts' requests are matrix-e2ee-cli's | `quote` in `A/_lib/admin_http.py` |
| A download replaces an existing file (CWE-59) | matrix-e2ee-cli sanitizes the file name and creates the file only when it does not exist; the wrapper refuses `--overwrite` | matrix-e2ee-cli `src/commands/download.rs`; `C/matrix-download-e2ee.py`, `C/test_e2ee_wrappers.py` |
| The takeover's hint names an unrelated process that reuses a stale pid | The pid comes from the old daemon's own status answer on its socket, not from a pid file | `running_daemon_pid` in `C/_lib/daemon_client.py`, used by `C/_lib/cutover.py`; `C/_lib/test_daemon_client.py` |
| An operator deactivates a user or encrypts a room by accident | `synapse-deactivate-user.py` and `synapse-migrate-room.py` print the plan and ask; without a terminal they refuse unless `--yes` is given | `A/synapse-deactivate-user.py`, `A/synapse-migrate-room.py`; `A/test_migrate_room.py` |
| A token kept in `config.json` has to be rotated or shared with the rest of the configuration | Tokens can come from the environment or a separate file; precedence environment, file, inline value | `resolve_tokens` in both `_lib/config.py`; `C/_lib/test_config.py`, `A/_lib/test_config.py` |
| A command runs through a shell with attacker-influenced text (CWE-78) | `subprocess` is called with argument lists and without `shell=True` (the E2EE binary in the wrappers, the takeover and the doctor, `dot` in the graph script) | `run` in `C/_lib/cli.py`, `migrate` in `C/_lib/cutover.py`, `C/matrix-doctor.py`, `A/synapse-graph.py` |
| A secret is committed | Betterleaks scans every push to `main` and every pull request to `main` | `.github/workflows/security.yml` |
| Insecure code or workflow patterns | Opengrep SAST fails on findings at the threshold the organisation's [static analysis rule](https://github.com/netresearch/.github/blob/main/SECURITY.md#static-analysis-sast) sets; zizmor analyses the workflows; ruff and ShellCheck run in Skill Validation | `.github/workflows/security.yml`, `.github/workflows/lint.yml` |
| A released archive is tampered with | The release workflow publishes a Cosign-signed `SHA256SUMS.txt` and build-provenance attestations | `.github/workflows/release.yml` (calls the skill-repo-skill release reusable) |

Which of these checks must pass before a pull request can merge is set in the branch protection of `main`, not in this repository.

## Secure design principles applied

- **Least privilege:** the chat scripts use a device and token of their own, separate from the user's clients; the admin token is needed only by `synapse-*` scripts; workflows start from `permissions: {}`.
- **Fail-safe defaults:** user deactivation and room migration refuse without a terminal or `--yes`; a check the doctor cannot complete reports "not verified", never OK (`C/matrix-doctor.py`); `matrix-e2ee-setup.py --logout` is refused rather than mapped to a server-side logout; a failed takeover runs no command (`C/_lib/cutover.py`).
- **Complete mediation of the store:** every command opens the store through matrix-e2ee-cli, which locks its data directory first.
- **Economy of mechanism:** every script in this repository uses only the Python standard library; end-to-end encryption is one external binary, pinned by hash.
- **Separation of secrets from configuration:** tokens may live in the environment or a token file (`resolve_tokens`); the E2EE token lives in matrix-e2ee-cli's session file, not in `config.json`.

## What a user cannot expect

- The configured homeserver is trusted. The scripts accept `http://` as well as `https://`; with `http://` the token travels unencrypted. TLS certificates are verified against the default trust store of `urllib` (the E2EE connections are matrix-e2ee-cli's); no certificate is pinned.
- The skill does not check the permissions of `config.json` or of a token file; protecting them is the user's job.
- The scripts act with the user's operating-system account. Any process of that account can read its tokens and store and use the daemon socket.
- Messages read from rooms are untrusted text. The skill cannot stop an agent from following instructions contained in them; that is a property of the agent (see `SECURITY-AUDIT.md`, W011, and `skills/matrix-communication/references/agent-governance.md`).
- Only deactivation and room migration ask for confirmation. `synapse-make-admin.py` (a permanent power level 100), `synapse-join-room.py`, `synapse-add-to-space.py`, `matrix-power-level.py`, and `matrix-redact.py` act as soon as they are called.
- Device trust recorded by version 3.1.8 or older stays in the store where it cannot be told apart: its direct send and edit scripts marked every device in a room verified. (The "ignored" marks its daemon stored count as unverified now.) The takeover from matrix-nio carries that local trust into matrix-e2ee-cli. Re-create the device (`matrix-e2ee-cli.py logout`, which also ends it on the server, then `matrix-e2ee-setup.py` and `matrix-key-backup.py --import-keys`) and verify your own devices again to start from a clean state.
- Sessions imported from the server-side key backup (`m.megolm_backup.v1`) are authenticated only by the backup's public key, as the algorithm defines; the homeserver could add sessions to the backup that decrypt as if they came from a room member. Restoring them is matrix-e2ee-cli's (matrix-sdk's) job.
- `synapse-search.py` sees only unencrypted events; an empty result does not mean there were no messages.
- The E2EE binary comes from the matrix-e2ee-cli GitHub release. The skill trusts the SHA-256 it pins, so a new binary needs a change of `C/_lib/cli_release.json` in this repository; no dependency review covers what that binary contains. `MATRIX_E2EE_CLI` runs any binary the user names, unchecked.
- The old matrix-nio store and the takeover backup stay on disk, with the device's access token and keys, until the user deletes them.
- `allowed-tools` in a `SKILL.md` pre-approves tools for the agent; it does not remove any tool the agent already has and is not a sandbox.
- Security fixes follow the supported-versions rules of the organisation's security policy; older releases may not receive them.
