---
name: matrix-announcement
description: "Use when composing a Matrix announcement — skill release, version bump, weekly digest, breaking-change heads-up, postmortem, RFC, multi-skill pipeline summary, or any agent-authored room post longer than a single line. Defines the HTML subset clients render, the type-tag system, glyph rules (no rockets, no party emoji), the m.text vs m.notice choice, and when to render an HTML card to PNG instead of cramming layout into formatted_body. Trigger before any matrix-send call that produces structured content. Companion to matrix-communication."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Pairs with matrix-communication for sending. Optional: headless Chromium for rendering HTML cards to PNG."
metadata:
  author: Netresearch DTT GmbH
  version: "1.21.1"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(chromium:*) Bash(curl:*) Bash(jq:*) Read Write
---

# Matrix Announcement

Content guidance for Matrix announcements; `matrix-communication` does the sending.

## The five rules

1. **One headline, one purpose.** A Matrix message is a tweet, not a blog post.
2. **Send `formatted_body` with the HTML subset.** `body` stays as plaintext fallback. Never send only Markdown — clients are not required to parse it.
3. **Lists beat paragraphs.** If you're tempted to write "and also …", start a `<ul>`.
4. **Code in `<pre><code>` blocks.** Commands, paths, version strings, IDs — every one of them.
5. **Layout > words → render an HTML card to PNG.** Comparisons, dashboards, multi-row tables die in `formatted_body`.

## Type tags (pick one — never stack)

| Tag | Meaning | Title example |
| --- | --- | --- |
| `New skill` | first public release | `New skill: github-release-skill v0.2.0` |
| `Release` | feature version | `Release: jira-skill v3.12.0` |
| `Patch` | bugfix-only | `Patch: docker-development-skill v1.7.0` |
| `Digest` | weekly / multi-skill roundup | `Digest: skill ecosystem — week of 2026-04-22` |
| `Heads-up` | breaking change, deprecation | `Heads-up: matrix-skill v2 drops Python 3.8` |
| `Postmortem` | incident summary | `Postmortem: CI cache wipe 2026-04-25` |
| `RFC` | proposal seeking feedback | `RFC: unified checkpoint schema` |

## Glyphs

One leading glyph at most. **Never** trailing decoration, multi-emoji ladders, 🚀, or 🎉. Approved: 🤖 bot · 📦 release · 🔧 tooling · 🛡 security · ⚠️ heads-up · 📋 digest · 🔬 RFC · 🚑 hotfix · 🔥 postmortem · ✨ new capability (sparingly).

## Pre-send checklist

- [ ] Title fits on one line in Element on a 1280-wide screen.
- [ ] First sentence states the change. No "we're excited to".
- [ ] Every URL wrapped in `<a>` with destination-as-text.
- [ ] Every command, path, version is in `<code>`.
- [ ] Multi-line code in `<pre><code class="language-…">`.
- [ ] At most one prefix glyph; no trailing emoji; no celebration.
- [ ] `body` is a real readable plaintext fallback, not stripped HTML.
- [ ] `msgtype` = `m.notice` for unattended automation, `m.text` otherwise.
- [ ] No `@room` unless it is an outage.
- [ ] Layout-heavy → card image with text fallback, not `<table>` in `formatted_body`.
- [ ] Length under 3000 chars or split into a thread.

## References

- [html-subset.md](references/html-subset.md) — allowed/banned tags, Markdown↔HTML, `data-mx-*` attributes
- [structure.md](references/structure.md) — skeleton, section patterns, element-when-to-use, length budget, `m.text` vs `m.notice`
- [glyphs.md](references/glyphs.md) — full glyph table with banned set
- [image-cards.md](references/image-cards.md) — chromium → upload → `m.image` recipe; image-pairing rules
- [threading.md](references/threading.md) — threads, mentions, edits, redactions
- [anti-patterns.md](references/anti-patterns.md) — wall-of-text, emoji ladder, mention storm, inline URLs (with fixes)
- [text-templates.md](references/text-templates.md) — drop-in `formatted_body` skeletons per type tag
- [templates/](references/templates/) — `release-card.html` (1200×630), `weekly-digest.html` (1200×1500), `comparison.html` (1200×900)
- [gallery.html](references/gallery.html) — visual preview of every rule, the five worked examples, and the three templates

Sending: pass the composed message to `matrix-communication` (`matrix-send-e2ee.py "$ROOM" "$MARKDOWN"`); the transport converts markdown to HTML using the rules in `html-subset.md`. For hand-crafted `formatted_body`, `m.notice` flagging, or `m.image` cards, call the homeserver API directly — recipe in `image-cards.md`.
