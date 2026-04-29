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
