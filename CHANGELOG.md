# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For the canonical narrative version of each release (rewritten after CI publishes the auto-generated notes), see the matching entry on the [releases page](https://github.com/netresearch/matrix-skill/releases).

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

## [1.22.0] - 2026-04-29

### Added

- **`matrix-announcement` skill** — third skill in the plugin, alongside `matrix-communication` (transport) and `matrix-administration` (Synapse ops). Content guidance for composing scannable, structured Matrix room announcements: HTML subset clients render, type-tag system (`Release` / `Patch` / `Heads-up` / `Digest` / `Postmortem` / `RFC` / `New skill`), glyph rules, `m.text` vs `m.notice` choice, and when to render an HTML card to PNG. Ships seven references, three rendered HTML card templates (1200×630 / 1200×1500 / 1200×900), 12 evals, and a visual gallery. No scripts. ([#31](https://github.com/netresearch/matrix-skill/pull/31))
- **`--notice` flag** on `matrix-send-e2ee.py` and `matrix-send.py` — sends `m.notice` instead of `m.text`, mutually exclusive with `--emote`. msgtype precedence: `notice > emote > text`. Closes the gap the announcement skill recommended but the transport scripts didn't support. ([#32](https://github.com/netresearch/matrix-skill/pull/32))

### Changed

- `matrix-send-e2ee.py` and `matrix-send.py`: `--emote` and `--notice` are now grouped via `argparse.add_mutually_exclusive_group`. The `send_message_e2ee()` and `send_message()` functions gained a `notice: bool = False` keyword parameter.
- `matrix-communication` quick-reference, `messaging-guide.md`, and the root `AGENTS.md` cheat-sheet updated to document `--notice`.
- `matrix-announcement/references/image-cards.md`: corrected guidance — `m.notice` is text-only; for an image announcement, send the card as `m.image` and a follow-up `m.text` via `--notice` rather than trying to flag the image event.

## [1.21.1] - 2026-04-29

Maintenance release: `matrix-administration` script harness improvements (10 → 18 checks), CI compatibility fixes, formatter robustness for pre-wrapped links and emphasis flanking.

## [1.21.0] - 2026-04-26

Quality overhaul of `matrix-administration`: 95% faster E2EE operations, 28 evals, expanded harness, full-text formatter improvements.

## [1.20.1] - 2026-04-22

Security patch: URL scheme validation before `urllib.urlopen` in `matrix-administration`.

## [1.20.0] - 2026-04-16

Added the **`matrix-administration` skill** — Synapse server operations (snapshot rooms, rate room health, render Graphviz map, force-join, promote, harden, deactivate, search history). Stdlib-only Python.

---

Older releases (before this changelog was introduced) are documented on the [releases page](https://github.com/netresearch/matrix-skill/releases).

[Unreleased]: https://github.com/netresearch/matrix-skill/compare/v1.22.0...HEAD
[1.22.0]: https://github.com/netresearch/matrix-skill/compare/v1.21.1...v1.22.0
[1.21.1]: https://github.com/netresearch/matrix-skill/compare/v1.21.0...v1.21.1
[1.21.0]: https://github.com/netresearch/matrix-skill/compare/v1.20.1...v1.21.0
[1.20.1]: https://github.com/netresearch/matrix-skill/compare/v1.20.0...v1.20.1
[1.20.0]: https://github.com/netresearch/matrix-skill/compare/v1.19.0...v1.20.0
