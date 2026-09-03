---
name: matrix-announcement
description: "Use when composing a Matrix announcement — skill release, version bump, weekly digest, breaking-change heads-up, postmortem, RFC, multi-skill pipeline summary, or any agent-authored room post longer than a single line. Trigger before any matrix-send call that produces structured content. Companion to matrix-communication."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Pairs with matrix-communication for sending. Optional: Chromium for HTML-card rendering."
metadata:
  author: Netresearch DTT GmbH
  version: "3.1.3"
  repository: https://github.com/netresearch/matrix-skill
allowed-tools: Bash(chromium:*) Bash(curl:*) Bash(jq:*) Read Write
---

# Matrix Announcement

Content rules for Matrix announcements. `matrix-communication` does the sending.

## The five rules

1. **One headline, one purpose.**
2. **`formatted_body` in the HTML subset, not Markdown.** `body` is the plaintext fallback — clients aren't required to parse Markdown.
3. **Lists beat paragraphs.** Enumerable items — findings, projects, failures, tickets — are a `<ul>`, however long each runs. A bold-led paragraph is emphasis, not structure.
4. **Wrap code — and name the thing itself.** Commands, paths, versions, IDs, env vars in `<code>`; multi-line in `<pre><code class="language-…">`. Name the identifier, not a category standing in for it (`html-subset.md`).
5. **Layout > words → render an HTML card to PNG.** Comparisons, dashboards and multi-row tables die in `formatted_body`.

## Type tags (pick one — never stack)

`New skill` first release · `Release` feature version · `Patch` bugfix-only · `Digest` weekly roundup · `Heads-up` breaking change or deprecation · `Postmortem` incident · `Findings` investigation or audit · `RFC` proposal seeking feedback

Findings reports group by category of finding, never by who was wrong (`structure.md`).

## Glyphs

One leading glyph at most. **Never** trailing decoration, multi-emoji ladders, 🚀, or 🎉. Approved: 🤖 bot · 📦 release · 🔧 tooling · 🛡 security · ⚠️ heads-up · 📋 digest · 🔬 RFC · 🚑 hotfix · 🔥 postmortem · 🔎 findings · ✨ new capability (sparingly).

## Pre-send checklist

- [ ] One-line title at 1280px, opening with the change — not "we're excited to".
- [ ] URLs wrapped in `<a>`, destination as text.
- [ ] Every entity is a link: issue keys (even mid-sentence), versions → release page, MRs/PRs (`project/path!N` / `org/repo#N`), pipelines, commits. Status updates: one item per line, linked key first, blank lines between.
- [ ] Rules 3–5 applied: list structure, code wrapped, one glyph at most.
- [ ] Findings headings name the category, not the person.
- [ ] `body` reads standalone, not stripped HTML.
- [ ] `m.notice` for unattended automation, `m.text` otherwise; no `@room` unless it is an outage.
- [ ] Under 3000 chars, or threaded; image card if layout-heavy.

## References

In `references/`:

- `html-subset.md` — allowed/banned tags, `data-mx-*`, naming the identifier
- `structure.md` — skeleton, length budget, `m.text` vs `m.notice`, **how to send**
- `glyphs.md` · `anti-patterns.md` — glyph table; wall-of-text, emoji ladder, mention storm
- `image-cards.md` — chromium → upload → `m.image`
- `threading.md` — threads, mentions, edits, redactions
- `text-templates.md` · `templates/` · `gallery.html` — skeletons, HTML cards, preview
