# Announcement structure

Every announcement, regardless of topic, has the same skeleton. Readers learn the rhythm and skim faster.

```
[icon] [Type tag]: [Subject] [— optional version]
[one-sentence why-this-matters]

[Section heading 1]
- bullet
- bullet

[Section heading 2]
- bullet

[Footer: links / tracking ticket / install command]
```

The icon and tag work like a subject-line prefix in email (`[SECURITY]`, `[RELEASE]`). They let humans and grep-style filters skim a busy room.

## Type tags

Pick one. Do not stack.

| Tag | Meaning | Title example |
| --- | --- | --- |
| `New skill` | first public release of a skill | `New skill: github-release-skill v0.2.0` |
| `Release` | new feature version of an existing skill | `Release: jira-skill v3.12.0` |
| `Patch` | bugfix-only bump | `Patch: docker-development-skill v1.7.0` |
| `Digest` | weekly / multi-skill roundup | `Digest: skill ecosystem — week of 2026-04-22` |
| `Heads-up` | breaking change, deprecation, migration | `Heads-up: matrix-skill v2 drops Python 3.8` |
| `Postmortem` | incident summary | `Postmortem: CI cache wipe 2026-04-25` |
| `RFC` | proposal looking for feedback | `RFC: unified checkpoint schema` |

## Section headings

Use **at most three** sections per message. Common patterns:

- **What it does / What it prevents / Install** — for new skill releases
- **New / Changed / Fixed** — for version bumps
- **Highlights / This week's releases / Open questions** — for digests
- **Symptom / Cause / Fix** — for postmortems
- **Why / How / Try it** — for proposals

Render headings as `<strong>Heading:</strong>` on its own line, or `<h3>` if the message is long enough to warrant TOC-style skimming. Avoid `<h2>`/`<h1>` (too loud).

## Sentence economy

- **First sentence states the change.** "X now does Y." Not "We are excited to announce that …".
- **Second sentence states the consequence.** "Existing tags continue to work; new tags require `-s`."
- **Skip the third sentence.** If you need it, it is a bullet.

## When to use which element

| Element | Use it for | Avoid for |
| --- | --- | --- |
| `<strong>` | the one word in a sentence the reader must not miss | every other word |
| `<code>` | commands, paths, identifiers, version strings, env vars, JSON keys | English nouns |
| `<pre><code>` | multi-line commands, JSON examples, diff snippets | one-liners |
| `<ul>` | 2–7 unordered items | a list of one — write a sentence |
| `<ol>` | numbered steps where order matters | bullets that just happen to have numbers |
| `<blockquote>` | quoting a user, an error, a previous decision | indenting for visual variety |
| `<table>` | tabular data ≥2 cols × ≥3 rows | two-column term/definition pairs |
| `<hr>` | separating an unrelated postscript | between every section (use spacing) |
| `<a>` | every URL — never paste raw URLs in `formatted_body` | "click here" — use the destination as text |
| `<br>` | a forced line break inside a paragraph | between paragraphs (use `<p>`) |

### Links: write what they are

```
✗ More info: <a href="…/issues/4365">here</a>
✓ Tracking: <a href="…/issues/4365">NRS-4365</a>
✓ Repo: <a href="https://github.com/netresearch/github-release-skill">github.com/netresearch/github-release-skill</a>
```

The link text should be the destination's identity (ticket, repo, doc title), not a verb.

## Length budget

| Metric | Target | Hard limit |
| --- | --- | --- |
| Title line | 6–12 words | 16 words |
| Lede sentence | 12–20 words | 30 words |
| Bullets per section | 3–5 | 7 |
| Sections per message | 2–3 | 4 |
| Total `formatted_body` length | ≤1500 chars | 3000 chars |
| Code blocks per message | ≤1 | 2 |

If you blow past the hard limit, you have a digest, not an announcement. Split it: short headline message in the room, full content in a thread or a linked doc.

## `m.text` vs `m.notice`

| `msgtype` | Use for | Why |
| --- | --- | --- |
| `m.notice` | Unattended automation: release announcements, CI summaries, scheduled digests, alert pings | Clients render it visually distinct (usually muted) and **bots are forbidden from auto-replying** to it — prevents bot-on-bot loops |
| `m.text` | Agent posting on behalf of a human who reviewed it (or a real human typing) | Default; replies welcome |
