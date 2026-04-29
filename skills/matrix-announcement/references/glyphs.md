# Iconography & emoji

Emoji are powerful as **prefix glyphs** and dangerous as decoration.

The rule: **one glyph at the front of the title**, optionally one inline glyph per bullet to mark category. Never trailing decoration. Never celebrations. The glyph carries meaning — if it doesn't, drop it.

## Approved prefix glyphs

| Glyph | Meaning | Use case |
| --- | --- | --- |
| 🤖 | bot | agent-authored announcement |
| 📦 | release | new feature version |
| 🔧 | tooling | infra, build, dev experience |
| 🛡 | security | CVE, hardening, lockdown |
| ⚠️ | heads-up | breaking change, deprecation |
| 📋 | digest | weekly / multi-skill roundup |
| 🔬 | RFC | proposal, request for comment |
| 🚑 | hotfix | urgent patch |
| 🔥 | postmortem | incident summary |
| ✨ | new capability | use sparingly; never on every release |

## Banned

| Glyph | Why |
| --- | --- |
| 🚀 | "It's a release, not a launchpad." Cheapens the message. |
| 🎉 | "Nobody is celebrating." Sounds like marketing. |
| 💯 | meaningless |
| 🔥 (as "cool") | reserved for postmortems |
| Multi-emoji ladders (🚀✨🎉, 🔥🔥🔥) | Always wrong. |
| Emoji as bullet markers (🟢 🟡 🔴) | Use a real `<ul>` and let the client style it. |

## Inline category glyphs

Inside a bullet, a leading 1-character category glyph is OK:

```
• ✨ new: progressive-disclosure refactor
• 🔧 changed: checkpoint runner hardened against ~10 edge cases
• 🐛 fixed: transitive dev-deps resolution
```

But **two glyphs in one bullet is a smell**. Pick the most important one or drop both.

## Why this matters

A coding agent posting `🚀✨🎉 NEW RELEASE!!! 🎉✨🚀` reads to humans as AI slop. The same announcement with `📦 Release: matrix-skill v1.20.0` reads as professional. The information content is identical; the emoji choice is the entire signal of seriousness.

When in doubt: **one glyph or none**.
