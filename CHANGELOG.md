# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the canonical narrative version of each release (rewritten after CI publishes the auto-generated notes), see the matching entry on the [releases page](https://github.com/netresearch/matrix-skill/releases).

## [Unreleased]

### Changed

- The shipped scripts are declared in `allowed-tools`, not the interpreter

### Fixed

- `matrix-administration`: corrected what the minted token is bound to

### Documentation

- `matrix-administration`: minting and diagnosing service tokens;
  `admin_request`'s token resolution quoted verbatim; the invisibility claim
  bounded and the probe trap named
- `matrix-announcement`: a maintenance-progress template, from a window that had none
- `troubleshooting`: backfill after a watcher gap; a store that "cannot be
  opened" is a backend mismatch
- Output escaping, and two limits on the recovery recipe

## [3.1.2] - 2026-08-27

### Fixed

- AGENTS.md kept under the 150-line index limit

### Documentation

- matrix-communication and matrix-announcement SKILL.md brought under the word cap

## [3.1.1] - 2026-08-17

### Fixed

- The fallback install hints in `_lib/deps.py` and the macOS workaround in the
  setup guide now pin `matrix-nio[e2e]<0.26` like the nine E2EE scripts and the
  doctor already did. Following the unpinned hints landed on 0.26/vodozemac, and
  the next `uv run` script then failed to open the store ([#109]).
- The backend-mismatch hint names the likely store rewriter: a script copy from
  an older skill version whose unpinned dependency resolves the newest
  matrix-nio. The generic hint had invited exactly that copy as a workaround
  ([#113]).

### Documentation

- `matrix-communication` gates multi-line sends on `matrix-announcement`, so
  structured posts get its content rules before delivery ([#110]).
- Device verification prefers `--listen`; `--request` is for the case of a
  single Element session ([#112]).

[#109]: https://github.com/netresearch/matrix-skill/issues/109
[#110]: https://github.com/netresearch/matrix-skill/issues/110
[#112]: https://github.com/netresearch/matrix-skill/issues/112
[#113]: https://github.com/netresearch/matrix-skill/issues/113

## [3.1.0] - 2026-08-13

### Documentation

- `SKILL.md` and `AGENTS.md` say how to read a room log: adjacent lines from one
  sender are adjacent events, and a reaction or redaction line names its target
  only when the daemon still holds it. Written after a summary turned four
  unrelated events into a story ([#104]).

## [3.0.0] - 2026-08-13

### Breaking

- **`synapse-migrate-room.py` asks before it changes anything** ([#102]). It read
  no state and asked no question: invoking it started a pipeline whose last step,
  enabling Megolm encryption, cannot be undone. It now reads the room's current
  state first, prints the steps it would take with the irreversible one marked,
  and stops for confirmation before the first write. `-y` / `--yes` skips the
  question, mirroring `synapse-deactivate-user.py`.

  Callers that run it from a script or a pipe now exit `2` with
  `Refusing to run non-interactively without --yes` until they pass `--yes`.
  Aborting at the prompt exits `1` and leaves the room untouched.

### Fixed

- **The room log records what a reaction reacts to and what a redaction removed**
  ([#104]). It recorded that they happened and nothing else, so a reader saw
  `reacted ✅️` and `removed a message` with no way to tell which message, or
  whether two such events were related. `matrix-watchd.py` dropped
  `ReactionEvent.reacts_to`, `RedactionEvent.redacts` and its `reason`; records
  now keep them, and the display line names the target when the daemon has it —
  `reacted ✅️ to "so bin beim RA"`. Beyond the last few hundred messages of a
  room the line falls back to its previous wording rather than printing an event
  id.

### Documentation

- README, `AGENTS.md` and `docs/ARCHITECTURE.md` describe the watch daemon, the
  `matrix-nio` pin and the store migration it forces.
- The live-awareness spec describes the relation fields a record carries and the
  window in which a target stays nameable.
- The safety guide, `SKILL.md` and `AGENTS.md` describe the confirmation gate
  both destructive `synapse-*` scripts now have.
- `skills/matrix-communication/README.md` points at the two license files that
  exist; the `LICENSE` it linked never did.

[#102]: https://github.com/netresearch/matrix-skill/issues/102
[#104]: https://github.com/netresearch/matrix-skill/issues/104

## [2.0.0] - 2026-08-13

### Breaking

- **`matrix-nio` is pinned below 0.26, and the pin is tied to the E2EE store.**
  0.26 sends the SAS commitment as a hex digest where 0.25 sent unpadded base64,
  so Element rejects every verification before it renders emoji
  ([matrix-nio#570](https://github.com/matrix-nio/matrix-nio/issues/570)). The
  two releases also use different crypto backends and write incompatible stores:
  opening one with the other fails as `OlmAccountError: BAD_ACCOUNT_KEY`, which
  names a key that was never the problem. An installation whose store was
  written by 0.26 must recreate it — the store cannot be migrated:

  ```bash
  matrix-e2ee-setup.py --logout && matrix-e2ee-setup.py
  matrix-key-backup.py --import-keys
  matrix-e2ee-verify.py --request DEVICE
  ```

- **Every path that opens the store now takes an exclusive lock.** Commands that
  previously ran beside each other, or beside the daemon, now wait and then
  refuse with the holder's pid. That is the point: two nio processes on one
  store corrupt it, and until now nothing stopped them. Commands routed through
  the daemon — send, react, redact, edit — keep working while it runs.

- **`matrix-e2ee-setup.py --logout` deletes only its own device's store files.**
  It globbed `*.db` and `*_devices` across the shared store directory, so
  logging one device out destroyed the megolm history of every other. Use
  `--purge-all` for the old behaviour.

### Added

- **Live room awareness.** `matrix-watchd.py` holds the E2EE store, syncs,
  decrypts and appends every event of a watched room to
  `rooms/<slug>.jsonl`; `matrix-watch.py` follows that log without touching the
  store, so any number of readers can run at once. Send, react, redact and edit
  route through the daemon's Unix socket when it is running and fall back to the
  direct path when it is not — no new flags, no second way to send a message.
  Rooms come from `watch_rooms` in the config. Design and plan in
  `docs/specs/` and `docs/exec-plans/completed/`.
- **Real mentions.** `--mention '@user:server'` (repeatable) and `--mention-room`
  set `m.mentions` (MSC3952), which is what notifies a modern client; a plain
  `@name` only ever matched the legacy push rule on an exact localpart. The pill
  goes into the HTML body, the plain body keeps the bare name.
- **A governance section in `SKILL.md`** on who turns the agent's function on,
  off or wider, and what a third party in a room may and may not decide.
- **A CI job that runs the unit tests.** They existed and nothing executed them.

### Fixed

- **`matrix-key-backup.py --import-keys` imported nothing.** It decrypted every
  session, discarded it, and counted it as imported. Three further defects sat
  in front of that: the AES-CBC IV was read off the ciphertext instead of the
  HKDF output, the MAC check rejected every backup written by a libolm client,
  and the backup key the script itself stores "for future use" had no code path
  that read it back.
- **`matrix-doctor.py` verified only the first token it found** and never asked
  the homeserver about the E2EE credential at all, so a deleted device reported
  `[OK] e2ee_setup` while every E2EE call failed with `Room not found`.
- **A fresh device could not verify.** nio cannot build a verification for a
  device it has no keys for, and the resulting error named the transaction
  rather than the missing device.
- **`self` in the event log marked the account, not the device.** An agent and
  the person it works for share one account, so the flag was true for both —
  useless for the one thing it exists for.
- **The E2EE guide recommended reusing a running client's access token.** That
  hijacks the client's device and breaks decryption in it, silently.

### Changed

- The event log renders an unknown display name as the localpart rather than the
  whole MXID, and the daemon remembers a name once it has seen it.
- `ruff` in `.pre-commit-config.yaml` matches the version CI runs.

## [1.28.0] - 2026-08-08

### Fixed

- **`matrix-doctor.py` reported a healthy setup for a token the homeserver
  rejects.** `check_config` only proved that `config.json` exists, parses, and
  carries `homeserver` and `user_id` — it never asked the homeserver anything, so
  an expired or revoked token still produced `[OK] config` and `All checks
  passed! Matrix Skill is ready to use.` while every authenticated call returned
  HTTP 401 `M_UNKNOWN_TOKEN`. A green doctor beside a 401 sends you looking for
  the problem everywhere except at the credential; worse, when the doctor's
  verdict stands in as evidence that something is fine, a dead token reads as
  "nothing to see" instead of "could not verify".

  A new `token` row asks `GET /_matrix/client/v3/account/whoami` and reports
  three states: accepted (and belonging to the configured `user_id`), rejected,
  or not verified. Not-verified renders as `[??]`, never `OK` — no token in the
  config is normal for E2EE use, `--offline` skips the call, and an unreachable
  homeserver is a missing answer. The summary line now names what it could not
  verify instead of claiming everything passed.

### Added

- **`matrix-doctor.py --offline`** skips the token check's homeserver call for
  air-gapped or CI runs; the row then reads "not verified" rather than OK.

## [1.27.1] - 2026-07-26

### Added

- matrix-communication: `references/hookshot-integration.md` — documents provisioning webhooks via the matrix-hookshot bridge bot (invite, promote to moderator, `!hookshot webhook <name>` command, retrieving the secret URL from the bot's admin DM), discovered via live testing ([#61](https://github.com/netresearch/matrix-skill/pull/61)).

## [1.27.0] - 2026-07-26

### Added

- matrix-communication: room management — `matrix-create-room.py` (create, with optional alias/topic/initial invites), `matrix-invite.py`, and `matrix-power-level.py` (`--show`/`--get`/`--set`, GET-modify-PUT against `m.room.power_levels`) ([#59](https://github.com/netresearch/matrix-skill/pull/59)).

## [1.25.4] - 2026-07-13

### Fixed

- matrix-announcement: resolve the cross-skill script path in SKILL.md ([#53](https://github.com/netresearch/matrix-skill/pull/53)).

### Documentation

- matrix-communication: `no-editorializing.md` now points at the canonical copy ([#54](https://github.com/netresearch/matrix-skill/pull/54)).
- matrix-announcement: trimmed SKILL.md generic bloat to meet the 500-word cap ([#53](https://github.com/netresearch/matrix-skill/pull/53)).

## [1.25.3] - 2026-07-01

### Documentation

- matrix-communication, matrix-announcement: added a "no editorializing" rule for messages and announcements — state what changed, not how good it is ([#51](https://github.com/netresearch/matrix-skill/pull/51)).

## [1.25.2] - 2026-06-27

### Fixed

- matrix-communication: E2EE own-device delivery and verification — don't report verification success on a MAC mismatch, and fetch room keys in `--listen` ([#47](https://github.com/netresearch/matrix-skill/pull/47), [#48](https://github.com/netresearch/matrix-skill/pull/48)).

### Documentation

- matrix-communication: gate E2EE device trust strictly on verification, with matrix-nio API notes ([#49](https://github.com/netresearch/matrix-skill/pull/49)).

## [1.25.1] - 2026-06-18

### Fixed

- matrix-communication: corrected misleading `brew install libolm` guidance in the setup guide and `_lib/deps.py` runtime error — `python-olm` has no macOS wheel and statically links its own bundled `libolm`, so Homebrew's library is never used. Documented the macOS 26 (Tahoe) / Apple Clang 17 build failure, a community-reported build-from-source workaround (GCC + `CMAKE_POLICY_VERSION_MINIMUM`), and the upstream status (libolm deprecated; vodozemac migration in `matrix-nio` PR [#555](https://github.com/matrix-nio/matrix-nio/pull/555)) ([#43](https://github.com/netresearch/matrix-skill/issues/43))

### Documentation

- matrix-administration: documented that room IDs may be passed without the `:server` suffix, and added the Synapse admin messages endpoint to the admin-API reference ([#45](https://github.com/netresearch/matrix-skill/pull/45)).

## [1.25.0] - 2026-06-10

### Added

- matrix-announcement: entity-linking rules (every issue key linked, versions link to their release page, MRs/PRs in `project/path!N` / `org/repo#N` notation) and one-item-per-line status-update layout ([#41](https://github.com/netresearch/matrix-skill/pull/41))

### Fixed

- matrix-communication: `[Unable to decrypt]` guidance now recommends `matrix-fetch-keys.py` first — resolves the common missing-room-keys case without a recovery key ([#41](https://github.com/netresearch/matrix-skill/pull/41))

## [1.24.0] - 2026-05-28

### Added

### Changed

### Fixed

### Removed

## [1.23.0] - 2026-05-15

### Added

- Ship as npm package via `@netresearch/agent-skill-coordinator` ([#37](https://github.com/netresearch/matrix-skill/pull/37))

### Fixed

- Declare both matrix skills in `aiAgentSkill` / `extra.ai-agent-skill`; include `.claude-plugin/plugin.json` in the npm tarball ([#37](https://github.com/netresearch/matrix-skill/pull/37))
## [1.22.0] - 2026-04-29

### Added

- **`matrix-announcement` skill** — third skill in the plugin, alongside `matrix-communication` (transport) and `matrix-administration` (Synapse ops). Content guidance for composing scannable, structured Matrix room announcements: HTML subset clients render, type-tag system (`Release` / `Patch` / `Heads-up` / `Digest` / `Postmortem` / `RFC` / `New skill`), glyph rules, `m.text` vs `m.notice` choice, and when to render an HTML card to PNG. Ships seven references, three rendered HTML card templates (1200×630 / 1200×1500 / 1200×900), 12 evals, and a visual gallery. No scripts. ([#31](https://github.com/netresearch/matrix-skill/pull/31))
- **`--notice` flag** on `matrix-send-e2ee.py` and `matrix-send.py` — sends `m.notice` instead of `m.text`, mutually exclusive with `--emote`. msgtype precedence: `notice > emote > text`. Closes the gap the announcement skill recommended but the transport scripts didn't support. ([#32](https://github.com/netresearch/matrix-skill/pull/32))

### Changed

- `matrix-send-e2ee.py` and `matrix-send.py`: `--emote` and `--notice` are now grouped via `argparse.add_mutually_exclusive_group`. The `send_message_e2ee()` and `send_message()` functions gained a `notice: bool = False` keyword parameter.
- `matrix-communication` quick-reference, `messaging-guide.md`, and the root `AGENTS.md` cheat-sheet updated to document `--notice`.
- `matrix-announcement/references/image-cards.md`: corrected guidance — `m.notice` is text-only; for an image announcement, send the card as `m.image` and a follow-up notice-flavour text message (msgtype `m.notice`, sent via `matrix-send-e2ee.py … --notice`) rather than trying to flag the image event itself as `m.notice`.

## [1.21.1] - 2026-04-29

Maintenance release: `matrix-administration` script harness improvements (10 → 18 checks), CI compatibility fixes, formatter robustness for pre-wrapped links and emphasis flanking.

## [1.21.0] - 2026-04-26

Quality overhaul of `matrix-administration`: 95% faster E2EE operations, 28 evals, expanded harness, full-text formatter improvements.

## [1.20.1] - 2026-04-22

Security patch: URL scheme validation before `urllib.request.urlopen` in `matrix-administration`.

## [1.20.0] - 2026-04-16

Added the **`matrix-administration` skill** — Synapse server operations (snapshot rooms, rate room health, render Graphviz map, force-join, promote, harden, deactivate, search history). Stdlib-only Python.

---

Older releases (before this changelog was introduced) are documented on the [releases page](https://github.com/netresearch/matrix-skill/releases).

[Unreleased]: https://github.com/netresearch/matrix-skill/compare/v3.1.1...HEAD
[3.1.1]: https://github.com/netresearch/matrix-skill/compare/v3.0.0...v3.1.1
[3.0.0]: https://github.com/netresearch/matrix-skill/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/netresearch/matrix-skill/compare/v1.28.0...v2.0.0
[1.28.0]: https://github.com/netresearch/matrix-skill/compare/v1.27.1...v1.28.0
[1.27.1]: https://github.com/netresearch/matrix-skill/compare/v1.27.0...v1.27.1
[1.27.0]: https://github.com/netresearch/matrix-skill/compare/v1.26.0...v1.27.0
[1.25.0]: https://github.com/netresearch/matrix-skill/compare/v1.24.0...v1.25.0
[1.24.0]: https://github.com/netresearch/matrix-skill/compare/v1.23.0...v1.24.0
[1.23.0]: https://github.com/netresearch/matrix-skill/compare/v1.22.0...v1.23.0
[1.22.0]: https://github.com/netresearch/matrix-skill/compare/v1.21.1...v1.22.0
[1.21.1]: https://github.com/netresearch/matrix-skill/compare/v1.21.0...v1.21.1
[1.21.0]: https://github.com/netresearch/matrix-skill/compare/v1.20.1...v1.21.0
[1.20.1]: https://github.com/netresearch/matrix-skill/compare/v1.20.0...v1.20.1
[1.20.0]: https://github.com/netresearch/matrix-skill/compare/v1.19.0...v1.20.0
