# Anti-patterns (with fixes)

## ✗ Wall of text

```
We're excited to announce that we've been working on something cool. The new
github-release-skill detects your project ecosystem (TYPO3, Node.js, Go, PHP,
skill repos) and finds all version files automatically, bumps versions
consistently, creates release branches, PRs, signed annotated tags...
```

### ✓ Structured

```
🤖 New skill: github-release-skill v0.2.0

Releases that don't burn tag names, skip CI, or end up as unsigned lightweights.

What it does:
• Detects ecosystem & bumps versions across all manifests
• Creates branches, PRs, signed annotated tags — full flow
• Rewrites auto-generated notes into a narrative

What it blocks:
• gh release create / delete
• Lightweight tags (git tag without -s)

Install: /install-plugin https://github.com/netresearch/github-release-skill
```

## ✗ Bold lead-in paragraphs

The wall of text above is easy to spot — it is marketing prose. This one is not: the
content is factual, linked, and correctly sectioned, so it reads as "already structured"
while writing. It still lands as a wall, because each finding is a paragraph that merely
*starts* with a bold word.

```
**Errors found**

**vemags** — MR !49 exists, but typo3:create-ticket fails: User 'x' cannot be
assigned issues. The script aborts via set -eu, so neither ticket nor automerge
happens. vemags stays on 13.4.32.

**bmdv** — bmdv/cms/main-13 is never picked up by the cron. In
generate-child-pipelines.sh:79 grep -v -F -f matches substrings without -x, so the
slow-repos.txt entry bmdv/cms/main swallows bmdv/cms/main-13 — no log entry.
```

### ✓ One finding, one list item

```html
<strong>Errors found</strong>
<ul>
  <li><strong>vemags</strong> — <a href="…/merge_requests/49">vemags/cms/main!49</a>
      exists, but <code>typo3:create-ticket</code> fails:
      <code>User 'x' cannot be assigned issues.</code> The script aborts via
      <code>set -eu</code>, so neither ticket nor automerge happens.</li>
  <li><strong>bmdv</strong> — <code>bmdv/cms/main-13</code> is never picked up by the
      cron. <a href="…#L79"><code>generate-child-pipelines.sh:79</code></a> uses
      <code>grep -v -F -f</code> without <code>-x</code>, so the
      <code>slow-repos.txt</code> entry <code>bmdv/cms/main</code> swallows
      <code>bmdv/cms/main-13</code>.</li>
</ul>
```

**The test:** if the items are enumerable — findings, projects, tickets, failures — they
are a `<ul>`, no matter how long each item is. Length is not a reason to drop the list;
it is the reason you need one. A bold word at the start of a paragraph is emphasis, not
structure: it gives the reader no left edge to scan down.

## ✗ Headings that name who was wrong

Reports that refute someone's assumptions get read by that someone. Headings framed
around the person turn a finding into a verdict.

```
**Real errors**          ← implies the reader's other points were fake
**Corrections**          ← "I am correcting you"
```

### ✓ Headings that name the category

```
**Errors found**
**No error, expected behaviour**
```

Name what the *system* did, not whose assumption failed. The facts underneath are
identical; only the framing changes, and the framing decides whether the facts get read.
Related but distinct from [no-editorializing](../../matrix-communication/references/no-editorializing.md):
that rule bans praising your own work, this one bans grading someone else's.

## ✗ Emoji ladder

```
🚀✨🎉 NEW RELEASE!!! 🎉✨🚀
We're SO excited to ship matrix-skill v1.20.0!!! 🔥🔥🔥
```

### ✓ One glyph, one purpose

```
📦 Release: matrix-skill v1.20.0
Media download + E2EE decryption.
```

## ✗ Inline raw URLs

```
See https://github.com/netresearch/peer-qa-review-skill for details.
```

### ✓ Linked, destination-as-text

```html
Repo: <a href="https://github.com/netresearch/peer-qa-review-skill">netresearch/peer-qa-review-skill</a>
```

## ✗ Three-column ASCII table

```
| Skill           | Old | New  |
|-----------------|-----|------|
| jira-skill      | 3.11| 3.12 |
| typo3-testing   | 5.13| 5.14 |
```

### ✓ HTML table — or, better, a digest card image

```html
<table>
  <thead><tr><th>Skill</th><th>From</th><th>To</th></tr></thead>
  <tbody>
    <tr><td><code>jira-skill</code></td><td>3.11</td><td>3.12</td></tr>
    <tr><td><code>typo3-testing-skill</code></td><td>5.13</td><td>5.14</td></tr>
  </tbody>
</table>
```

For more than three rows, render `templates/weekly-digest.html` to PNG and post it as `m.image` instead.

## ✗ Mention storm

```
cc @alice @bob @carol @dave @everyone — please review
```

### ✓ One owner, named for a reason

```
Owner: @sebastian — review by Friday for the v3.13 cut.
```

## ✗ Unannounced breaking change

```
Release: matrix-skill v2.0.0
- many improvements
```

### ✓ `Heads-up` tag, migration in the message

```
⚠️ Heads-up: matrix-skill v2.0.0 — breaking

Drops Python 3.8 (EOL). Minimum is now 3.10.

Migration: bump your venv before installing v2.
Old v1.x line continues to receive security patches until 2026-12-31.
```

## A worked example — three ways

### ✗ A paragraph

> Hey team, just wanted to share that we shipped a new version of matrix-skill (v1.20.0) which now supports media download from Matrix rooms including E2EE-encrypted files, and also we updated jira-skill to v3.10.0 with attachment upload support, so now you can do the full pipeline of pulling images out of matrix rooms and attaching them to jira tickets, here's how it works...

### ◯ Text-only structured (acceptable)

```html
<p>📦 <strong>New: Matrix → Jira attachment pipeline</strong></p>
<p>Media from Matrix rooms (incl. E2EE) can now flow into Jira issues.</p>

<p><strong>3 commands, full pipeline:</strong></p>
<pre><code class="language-bash"># 1. Find media in room
matrix-read-e2ee.py ROOM --json

# 2. Download &amp; decrypt
matrix-download-e2ee.py ROOM $EVENT_ID --output /tmp

# 3. Attach to Jira
jira-attachment.py add PROJ-123 /tmp/image.png</code></pre>

<p><strong>Releases:</strong></p>
<ul>
  <li><code>matrix-skill</code> v1.20.0 — media download + E2EE decryption</li>
  <li><code>jira-skill</code> v3.10.0 — attachment upload, --reporter flag</li>
</ul>
```

### ✓ Card image + short text (best)

1. Render `templates/release-card.html` with the title "Matrix → Jira", the three commands, and the two version pills.
2. Send `m.image` with that PNG. `body` is the plaintext version above.
3. Follow with a one-line `m.text`:

```html
<p>Docs: <a href="…">matrix-skill v1.20.0</a> · <a href="…">jira-skill v3.10.0</a></p>
```
