# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the canonical narrative version of each release (rewritten after CI publishes the auto-generated notes), see the matching entry on the [releases page](https://github.com/netresearch/matrix-skill/releases).

## [Unreleased]

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

[Unreleased]: https://github.com/netresearch/matrix-skill/compare/v1.25.0...HEAD
[1.25.0]: https://github.com/netresearch/matrix-skill/compare/v1.24.0...v1.25.0
[1.24.0]: https://github.com/netresearch/matrix-skill/compare/v1.23.0...v1.24.0
[1.23.0]: https://github.com/netresearch/matrix-skill/compare/v1.22.0...v1.23.0
[1.22.0]: https://github.com/netresearch/matrix-skill/compare/v1.21.1...v1.22.0
[1.21.1]: https://github.com/netresearch/matrix-skill/compare/v1.21.0...v1.21.1
[1.21.0]: https://github.com/netresearch/matrix-skill/compare/v1.20.1...v1.21.0
[1.20.1]: https://github.com/netresearch/matrix-skill/compare/v1.20.0...v1.20.1
[1.20.0]: https://github.com/netresearch/matrix-skill/compare/v1.19.0...v1.20.0
