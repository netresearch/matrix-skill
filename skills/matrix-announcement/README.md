# Matrix Announcement

Content-design guidance for coding agents posting into Matrix rooms — release notes, version bumps, weekly digests, breaking-change heads-ups, postmortems, RFCs, multi-skill pipeline summaries. Companion to **matrix-communication** in this repo (which transports the message you compose here).

## Why this skill

A Matrix room with five active bots quickly becomes unreadable when each one posts walls-of-text or `🚀✨🎉 NEW RELEASE!!! 🎉✨🚀`. This skill defines:

- The HTML subset Matrix clients actually render
- A type-tag system (`Release`, `Patch`, `Heads-up`, `Digest`, `Postmortem`, `RFC`, `New skill`) so a busy room can be skimmed
- Glyph rules — one leading glyph max, no rockets, no party emoji
- The `m.text` vs `m.notice` choice
- When to render an HTML card to PNG instead of cramming layout into `formatted_body`
- Drop-in templates and a visual gallery

## Features

- **Slim SKILL.md** — five rules + type-tag table + pre-send checklist, kept within 500-word target
- **Six reference guides** — html-subset, structure, glyphs, image-cards, threading, anti-patterns
- **Seven drop-in `formatted_body` skeletons** — release, new-skill, digest, heads-up, postmortem, RFC, patch
- **Three rendered HTML card templates** — `release-card.html` (1200×630), `weekly-digest.html` (1200×1500), `comparison.html` (1200×900). Render headlessly with Chromium, upload, post as `m.image`.
- **Visual gallery** — `references/gallery.html` previews every rule, all five worked examples, and the three templates in one page

## Installation

### Via the Netresearch marketplace (recommended)

```bash
/plugin marketplace add netresearch/claude-code-marketplace
```

Then `/install-plugin netresearch/matrix-skill`. Ships alongside `matrix-communication` and `matrix-administration`.

### Via release download

Grab the [latest release](https://github.com/netresearch/matrix-skill/releases/latest) and extract to `~/.claude/skills/matrix-announcement/`.

## Usage

The skill triggers on any agent-authored Matrix post longer than a single line. Examples:

```
"Announce the vX.Y.Z release in #releases:example.com"
"Post the weekly skill digest"
"Heads-up the team that matrix-skill v2 drops Python 3.8"
"Render a comparison card for the new auth flow and post it"
```

The skill defines what to put inside the message; `matrix-communication` ships it.

## Rendering a PNG card

```bash
chromium --headless=new --hide-scrollbars \
  --window-size=1200,630 \
  --screenshot=card.png \
  "file://$(pwd)/skills/matrix-announcement/references/templates/release-card.html"
```

Substitute `{{PLACEHOLDER}}` values in the template before rendering. Full upload + `m.image` recipe in `references/image-cards.md`.

## Structure

```
matrix-announcement/
├── SKILL.md                            # AI instructions
├── README.md                           # this file
├── LICENSE                             # → ../../LICENSE-MIT (and CC-BY-SA-4.0)
├── evals/evals.json                    # behavior expectations
└── references/
    ├── html-subset.md                  # allowed/banned tags, Matrix-specific attrs
    ├── structure.md                    # skeleton, type tags, length budget
    ├── glyphs.md                       # iconography, banned set
    ├── image-cards.md                  # chromium → upload → m.image recipe
    ├── threading.md                    # threads, mentions, edits, redactions
    ├── anti-patterns.md                # bad/good comparisons + worked example
    ├── text-templates.md               # 7 drop-in formatted_body skeletons
    ├── gallery.html                    # visual preview of all rules + examples
    └── templates/
        ├── release-card.html
        ├── weekly-digest.html
        └── comparison.html
```

## License

Code: MIT. Documentation: CC-BY-SA-4.0. SPDX: `(MIT AND CC-BY-SA-4.0)`. See repo-level `LICENSE-MIT` and `LICENSE-CC-BY-SA-4.0`.
