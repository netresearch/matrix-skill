# Text-only `formatted_body` templates

Drop-in skeletons. Substitute `{placeholders}`. Each is paired with a `body` plaintext fallback.

## Single-skill release

```html
<p>📦 <strong>Release:</strong> <code>{skill}</code> v{version}</p>
<p>{one-sentence summary of what this version is about}.</p>

<p><strong>What's new:</strong></p>
<ul>
  <li>{change 1}</li>
  <li>{change 2}</li>
  <li>{change 3}</li>
</ul>

<p><strong>Install:</strong> <code>/install-plugin {repo-url}</code><br/>
<strong>Repo:</strong> <a href="{repo-url}">{org}/{repo}</a><br/>
<strong>Tracking:</strong> <a href="{ticket-url}">{ticket-id}</a></p>
```

Plaintext `body`:

```
Release: {skill} v{version}
{one-sentence summary}.

What's new:
- {change 1}
- {change 2}
- {change 3}

Install: /install-plugin {repo-url}
Repo: {repo-url}
Tracking: {ticket-id} {ticket-url}
```

## New skill announcement

```html
<p>🤖 <strong>New skill:</strong> <code>{skill}</code> v{version}</p>
<p>{problem this skill solves, in one sentence}.</p>

<p><strong>What it does:</strong></p>
<ul>
  <li>{capability 1}</li>
  <li>{capability 2}</li>
</ul>

<p><strong>What it prevents:</strong></p>
<ul>
  <li><code>{blocked-command}</code> — {why}</li>
</ul>

<p><strong>Install:</strong> <code>/install-plugin {repo-url}</code></p>
```

## Weekly digest (text version — but consider a card image)

```html
<p>📋 <strong>Skill ecosystem update</strong> — releases since {date-range}</p>

<p><strong>New skills this week:</strong></p>
<ul>
  <li><code>{skill}</code> v{version} — {one-line description}</li>
</ul>

<p><strong>Releases ({n} repos):</strong></p>
<ul>
  <li><code>{skill}</code> v{version} — {what changed}</li>
</ul>

<p><strong>Patches:</strong></p>
<ul>
  <li><code>{skill}</code> v{version}</li>
</ul>
```

For more than ~6 lines of releases, render `templates/weekly-digest.html` to PNG and post that instead.

## Heads-up / breaking change

```html
<p>⚠️ <strong>Heads-up:</strong> <code>{skill}</code> v{version} — {what breaks}</p>
<p>{one-sentence why}.</p>

<p><strong>What changes:</strong> {concrete behavior diff}.</p>
<p><strong>Migration:</strong> {steps the reader must take}.</p>
<p><strong>Timeline:</strong> {when old behavior goes away}.</p>
<p><strong>Help:</strong> <a href="{thread-or-issue}">{ticket-id}</a></p>
```

## Maintenance progress (one per phase, incident and resolution)

A window room is read by people who are not in your terminal. They need to know,
per message: which ticket, what state, whether it affects them, and what happens
next. In that order, and skimmable in about five seconds.

```html
<p>{🔧|✅|⛔|↩️} <a href="{ticket-url}">{TICKET-KEY}</a> — <strong>{RUNNING|DONE|BLOCKED|ROLLED BACK}</strong>: {what, in one clause}</p>
<p><strong>Impact:</strong> {who notices what, or "none"}.</p>
<p><strong>Next:</strong> {the next step and roughly when}.</p>
<details><summary>Output</summary><pre>{gate output, if any}</pre></details>
```

Every ticket, MR and tag is a link. A bare key is a lookup you have handed to
the reader; one window produced six messages naming 26 keys with zero links.

Anti-patterns this template exists to prevent, all observed in one window:

- **Opening with a tool tally.** `PLAY RECAP … ok=14 changed=2` as line one tells
  a colleague nothing. The state token does.
- **The 3000-character wall.** If it does not fit the shape above, it is a
  ticket comment, not a room message — post the comment and link it.
- **Silence between the announcement and the result.** A phase that starts gets
  a message; the same phase ending gets another. The room was silent through
  56 % of that session, including the riskiest action of the night.
- **Announcing an expected state.** Say what you measured. One announcement
  claimed a service was live on its new path; the measurement that contradicted
  it arrived 1h46m later.
- **Correcting yourself in a new message.** Edit the original
  (`matrix-edit-e2ee.py`) so a reader arriving later sees one true version
  rather than reconstructing which of two stands.

## Postmortem

```html
<p>🔥 <strong>Postmortem:</strong> {what failed} on {date}</p>
<blockquote>
  <p><strong>Impact:</strong> {who was affected, for how long}.</p>
</blockquote>

<p><strong>Symptom:</strong> {observed behavior}.</p>
<p><strong>Cause:</strong> {root cause in one sentence}.</p>
<p><strong>Fix:</strong> {what was done}.</p>
<p><strong>Follow-up:</strong> <a href="{ticket}">{ticket-id}</a></p>
```

## Findings (investigation / audit result)

Headings name the category of finding, never who was wrong. One `<li>` per finding, however long the item runs.

```html
<p>🔎 <strong>Findings:</strong> {what was checked}</p>
<p>{one-sentence verdict: what ran, how much of it worked}.</p>

<p><strong>Errors found:</strong></p>
<ul>
  <li><strong>{subject}</strong> — {what fails}: <code>{error}</code>. {consequence}.</li>
  <li><strong>{subject}</strong> — {what fails}. {cause, with a link to the line}.</li>
</ul>

<p><strong>No error, expected behavior:</strong></p>
<ul>
  <li><strong>{subject}</strong> — {why it looked broken but is not}.</li>
</ul>

<p><strong>Next steps:</strong></p>
<ul>
  <li>{action}, tracked in <a href="{ticket}">{ticket-id}</a>.</li>
</ul>
```

## RFC

```html
<p>🔬 <strong>RFC:</strong> {proposal title}</p>
<p>{one-sentence problem statement}.</p>

<p><strong>Why:</strong> {motivation}.</p>
<p><strong>How:</strong> {sketch of the approach}.</p>
<p><strong>Try it:</strong> <code>{command or branch}</code></p>
<p><strong>Feedback by:</strong> {date}, in <a href="{thread}">this thread</a>.</p>
```

## Patch (bugfix-only)

```html
<p>🚑 <strong>Patch:</strong> <code>{skill}</code> v{version}</p>
<p>{one-sentence bug summary}.</p>
<p><strong>Fixed:</strong> {what was wrong} → {what is now correct}.<br/>
<strong>Affected:</strong> {who needs to upgrade}.</p>
```
