---
name: matrix-announcement
description: "Use when composing a Matrix announcement — skill release, version bump, weekly digest, breaking-change heads-up, postmortem, RFC, multi-skill pipeline summary, or any agent-authored room post longer than a single line. Trigger before any matrix-send call that produces structured content. Companion to matrix-communication."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Pairs with matrix-communication for sending. Optional: Chromium for HTML-card rendering."
metadata:
  author: Netresearch DTT GmbH
  version: "3.0.0"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(chromium:*) Bash(curl:*) Bash(jq:*) Read Write
---

# Matrix Announcement

Content rules for Matrix announcements: HTML subset, type tags, glyphs, `m.text`/`m.notice`, PNG-card threshold. `matrix-communication` does the sending.

## The five rules

1. **One headline, one purpose.**
2. **`formatted_body` in the HTML subset, not Markdown.** `body` is the plaintext fallback — clients aren't required to parse Markdown.
3. **Lists beat paragraphs.** Enumerable items — findings, projects, failures, tickets — are a `<ul>`, however long each item runs. A paragraph opening with a bold word is emphasis, not structure.
4. **Wrap code.** Commands, paths, versions, IDs, env vars in `<code>`; multi-line in `<pre><code class="language-…">`.
5. **Layout > words → render an HTML card to PNG.** Comparisons, dashboards, multi-row tables die in `formatted_body`.

## Type tags (pick one — never stack)

- `New skill` — first public release
- `Release` — feature version
- `Patch` — bugfix-only
- `Digest` — weekly / multi-skill roundup
- `Heads-up` — breaking change, deprecation
- `Postmortem` — incident summary
- `Findings` — result of an investigation or audit
- `RFC` — proposal seeking feedback

Findings reports group by category of finding (`Errors found`, `No error, expected behavior`), never by who was wrong (`Real errors`, `Corrections`).

## Glyphs

One leading glyph at most. **Never** trailing decoration, multi-emoji ladders, 🚀, or 🎉. Approved: 🤖 bot · 📦 release · 🔧 tooling · 🛡 security · ⚠️ heads-up · 📋 digest · 🔬 RFC · 🚑 hotfix · 🔥 postmortem · 🔎 findings · ✨ new capability (sparingly).

## Pre-send checklist

- [ ] One-line title, Element at 1280px.
- [ ] Opens with the change, not "we're excited to".
- [ ] URLs wrapped in `<a>`, destination as text.
- [ ] Every entity is a link: issue keys (even mid-sentence), versions → release page, MRs/PRs (`project/path!N` / `org/repo#N`), pipelines, commits. Status updates: one item per line, linked key first, blank lines between.
- [ ] Enumerable items in a `<ul>`, not bold-led paragraphs (rule 3).
- [ ] Findings headings name the category, not the person.
- [ ] Code wrapped (rule 4).
- [ ] Glyph OK (rules above).
- [ ] `body` reads standalone, not stripped HTML.
- [ ] `msgtype` = `m.notice` for unattended automation, `m.text` otherwise.
- [ ] No `@room` unless it is an outage.
- [ ] Image card if layout-heavy (rule 5).
- [ ] Length under 3000 chars or split into a thread.

## References

- [html-subset.md](references/html-subset.md) — allowed/banned tags, `data-mx-*` attributes
- [structure.md](references/structure.md) — skeleton, type-tag examples, length budget, `m.text` vs `m.notice`
- [glyphs.md](references/glyphs.md) — glyph table, banned set
- [image-cards.md](references/image-cards.md) — chromium → upload → `m.image` recipe
- [threading.md](references/threading.md) — threads, mentions, edits, redactions
- [anti-patterns.md](references/anti-patterns.md) — wall-of-text, emoji ladder, mention storm
- [text-templates.md](references/text-templates.md) — drop-in skeletons per type tag
- [templates/](references/templates/) — three HTML card templates
- [gallery.html](references/gallery.html) — visual preview of rules and templates

Sending: `matrix-communication` ships it (`${CLAUDE_SKILL_DIR}/../matrix-communication/scripts/matrix-send-e2ee.py "$ROOM" "$MARKDOWN" [--notice]`), converting markdown to HTML per `html-subset.md`. `--notice` marks automation, exclusive of `--emote`. Hand-crafted `formatted_body`/`m.image`: call the homeserver API — recipe in `image-cards.md`.
