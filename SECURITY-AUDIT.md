# Security Audit Notes

## Known Scanner Findings (False Positives)

### Snyk W007 — HIGH: "Insecure credential handling" (plaintext recovery key)

**Status:** False positive. Truncated placeholder example.

The SKILL.md and `matrix-key-backup.py` contain `"EsTj ..."` and `"EsTj qRGp ..."` as placeholder examples showing CLI argument format. These are not actual recovery keys — they are truncated with `...` to indicate the user should provide their own key at runtime. The script correctly accepts recovery keys only as CLI arguments, never stores them in files or code.

### Snyk W011 — MEDIUM: Third-party content exposure from Matrix messages

**Status:** By design. Matrix messages are the skill's primary data source. Content isolation between external messages and agent instructions is a platform-level concern, not addressable at the skill level without breaking core functionality.
