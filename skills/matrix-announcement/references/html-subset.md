# The HTML subset Matrix clients render

The Matrix spec defines an explicit allow-list. Element, Cinny, FluffyChat all converge on roughly the same set. Treat this as the floor — if it's not on the allow-list, assume the client strips it silently.

## Allowed

**Inline:** `<a>`, `<b>`, `<i>`, `<u>`, `<strong>`, `<em>`, `<code>`, `<del>`, `<strike>`, `<sub>`, `<sup>`, `<br>`, `<span>`

**Block:** `<p>`, `<div>`, `<blockquote>`, `<pre>`, `<hr>`, `<h3>`–`<h6>`

**Lists:** `<ul>`, `<ol>`, `<li>`

**Tables:** `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`, `<caption>`

**Matrix-specific:**

- `<span data-mx-color="#…">` and `data-mx-bg-color` for color
- `<span data-mx-spoiler="reason">` for spoilers
- `<a href="https://matrix.to/#/@user:server">@user</a>` for mentions
- `<mx-reply>` — client-injected on rich replies; never write it yourself
- `<pre><code class="language-bash">` — Element renders syntax highlighting; common classes: `language-bash`, `language-python`, `language-json`, `language-diff`, `language-yaml`

## Banned (silently stripped)

- `<script>`, `<iframe>`, `<form>`, `<style>` — entire elements removed
- `style="…"` attributes — beyond `data-mx-*`, all inline CSS is stripped
- `<img src="https://…">` from arbitrary URLs — images go in via `m.image` events with `mxc://` URIs
- `<video>`, `<audio>` — same; use `m.video` / `m.audio` events
- `class="…"` — mostly stripped (Element keeps `language-…` on `<code>`)
- `<h1>`, `<h2>` — technically allowed but render as system-banner-loud in Element. Start at `<h3>` in practice.

## Markdown vs HTML — pick one and convert

If your skill composes in Markdown internally, run it through a real converter (markdown-it, commonmark) to produce `formatted_body`. **Do not** send raw Markdown in `formatted_body` and hope the client renders it — most do not.

`body` may keep the Markdown-ish look (backticks, `-` bullets) — that is fine and even helpful for plaintext readers.

## `body` is not optional

Notifications, push alerts, screen readers, search indexes, IRC/XMPP bridges, and CLI Matrix clients all read `body`, not `formatted_body`. Write it as a real readable message, not stripped HTML. Two good patterns:

- **Strip-and-keep** — drop tags, keep newlines, keep punctuation. Bullet glyphs (`•`, `-`) stay in. Code stays unfenced but with backticks.
- **Short summary** — when the HTML is dense (tables, cards), set `body` to a one- or two-line summary plus a link.

## A minimal rich event

```json
{
  "msgtype": "m.text",
  "format":  "org.matrix.custom.html",
  "body":    "Release: github-release-skill v0.2.0\nRepo: https://github.com/netresearch/github-release-skill",
  "formatted_body": "<p><strong>Release:</strong> <code>github-release-skill</code> v0.2.0<br/>Repo: <a href=\"https://github.com/netresearch/github-release-skill\">netresearch/github-release-skill</a></p>"
}
```

Two fields decide rendering: `body` (plaintext fallback — required) and `formatted_body` (HTML, only when `format` is set).
