# When to render an HTML card to PNG

`formatted_body` is fine for prose, lists and short tables. It is **bad** at:

- Comparisons (matrix client X vs Y, before/after, plan tiers)
- Dashboards (test counts, coverage deltas, dependency health)
- Timelines (release calendar, incident timeline)
- Anything with column alignment beyond ~3 columns
- Anything that needs color-coded status pills, badges, or icons
- Hero / announce cards for major releases where visual identity helps the message survive scrolling

For these: **design an HTML card → render to PNG headlessly → upload to the homeserver → post as `m.image`**. The plaintext `body` becomes the searchable fallback.

## The recipe

```bash
# 1. Render
chromium --headless=new \
  --disable-gpu \
  --hide-scrollbars \
  --window-size=1200,630 \
  --screenshot=card.png \
  --default-background-color=00000000 \
  "file://$(pwd)/card.html"

# 2. Upload to homeserver → mxc:// URI
MXC=$(curl -s -X POST \
  -H "Authorization: Bearer $MATRIX_TOKEN" \
  -H "Content-Type: image/png" \
  --data-binary @card.png \
  "$HOMESERVER/_matrix/media/v3/upload?filename=card.png" \
  | jq -r .content_uri)

# 3. Send m.image (file size via wc -c so it works on both Linux and macOS;
#    `stat -c%s` is GNU-only, `stat -f%z` is BSD-only — wc -c < FILE is portable)
SIZE=$(wc -c < card.png | tr -d ' ')
curl -s -X PUT \
  -H "Authorization: Bearer $MATRIX_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"msgtype\": \"m.image\",
    \"body\": \"github-release-skill v0.2.0 — release card\",
    \"url\": \"$MXC\",
    \"info\": {
      \"mimetype\": \"image/png\",
      \"w\": 1200,
      \"h\": 630,
      \"size\": $SIZE
    }
  }" \
  "$HOMESERVER/_matrix/client/v3/rooms/$ROOM/send/m.room.message/$(uuidgen)"

# 4. Follow with the text/links nobody can copy from an image.
#    ${CLAUDE_SKILL_DIR} is substituted by Claude Code to the active skill's
#    directory; the matrix-communication scripts live one directory up.
#    Do NOT quote it — it is a literal substitution, not a shell variable.
uv run ${CLAUDE_SKILL_DIR}/../matrix-communication/scripts/matrix-send-e2ee.py "$ROOM" \
  '**Install:** `/install-plugin https://github.com/netresearch/github-release-skill`'
```

> **Note:** The `matrix-communication` transport sends `m.text` with markdown-converted HTML. For unattended automation that should be `m.notice` (and therefore unreplyable by other bots), use the raw `PUT /_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}` call shown in step 3 with `"msgtype": "m.notice"`.

## Why "design HTML, render to PNG" beats "have the LLM make an image"

- HTML/CSS gives pixel-precise control over typography, spacing, color
- The same template renders deterministically every week — diffs are obvious, regressions catchable
- Coding agents are excellent at writing HTML and bad at generating rasters; lean into the strength
- Templates are reviewable code (`templates/release-card.html`), not disposable prompts

## Three templates

| Template | Use for | Size |
| --- | --- | --- |
| `templates/release-card.html` | single-skill release announcements | 1200×630 |
| `templates/weekly-digest.html` | multi-skill weekly roundups | 1200×1500 |
| `templates/comparison.html` | before/after, vs-tables, migration deltas | 1200×900 |

Each is a self-contained HTML file with `{{PLACEHOLDER}}` substitutions the calling skill replaces before rendering. Open `gallery.html` for a live preview.

## Always pair the image with text

An `m.image` event alone is hostile to:

- screen-reader users
- mobile users on metered connections
- anyone scrolling search results
- anyone trying to copy the install command

Either set the image's `body` to the full plaintext fallback the announcement would have been, **or** send the card and immediately follow with a short `m.text` containing the links and commands.

```json
{
  "msgtype": "m.image",
  "body": "Release: github-release-skill v0.2.0\n\nWhat's new:\n- detects ecosystem & bumps versions\n- signed annotated tags only\n- rewrites release notes into narrative\n\nInstall: /install-plugin https://github.com/netresearch/github-release-skill\nRepo: https://github.com/netresearch/github-release-skill",
  "url": "mxc://netresearch.de/abc123…",
  "info": { "w": 1200, "h": 630, "mimetype": "image/png", "size": 184223 }
}
```
