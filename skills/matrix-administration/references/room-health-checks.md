# Room health checks

`synapse-rate-rooms.py` and `synapse-graph.py` each run every room through the same set of checks (see `_lib/rating.py`). Results are graded:

- ✅ **SUCCESS** — the rule is satisfied.
- ⚠️ **WARNING** — minor / advisory.
- ❌ **FAIL** — serious or blocking.

The overall room rating is the worst result across all applicable rules.

## Why "home spaces"?

Several checks compare each room to a list of spaces you consider "home" — passed via `--space '!ID:server'` (repeatable) or via `home_space_ids` / `default_space_id` in the config. **The skill ships no homeserver-specific data**; if you do not pass any space IDs, the in-space checks are skipped (no FAIL/WARN, no SUCCESS).

## Rules — non-space rooms

| Rule | Result | What it means | How to fix |
|------|--------|--------------|------------|
| `Is a public room` | ❌ FAIL | `m.room.join_rules` is `public` — anyone on the federation can join. | Switch to `restricted` or `invite` (or use `synapse-migrate-room.py`). |
| `Joinable from our spaces` | ✅ SUCCESS | Room is `restricted` and at least one allow entry is a home space. | — |
| `Not joinable from our spaces` | ❌ FAIL | Room is `restricted` but no allow entry is a home space. | Add the relevant home space to `m.room.join_rules.allow`. |
| `In one of our spaces` | ✅ SUCCESS | Some home space lists this room as `m.space.child`. | — |
| `Not in one of our spaces` | ⚠️ WARNING | No home space lists this room. | `synapse-add-to-space.py`. |
| `Predecessor was in one of our spaces` | ❌ FAIL | The room replaced an older one (`m.room.tombstone`) that was in a home space; the new room isn't. | Re-link the new room into the parent space. |
| `Encrypted` | ✅ SUCCESS | `m.room.encryption` is set. | — |
| `Not encrypted` | ⚠️ WARNING | Room transmits messages in plaintext. | Enable encryption (irreversible — see safety guide). |

## Rules — spaces

| Rule | Result | What it means | How to fix |
|------|--------|--------------|------------|
| `Is a public space` | ❌ FAIL | `m.room.join_rules` on the space is `public`. | Switch to `invite` or `restricted`. |
| `One of our spaces` | ✅ SUCCESS | Space ID is listed in `home_space_ids`. | — |
| `Not one of our spaces` | ⚠️ WARNING | Space exists on the homeserver but isn't part of your home tree. | Add it to `home_space_ids` if it should be, or leave it. |

## Restricted joins and room version

The `restricted` join rule requires room version > 9 (Matrix v1.2). Older rooms cannot use it; `synapse-migrate-room.py` skips the join-rule step and prints a red ❌ when this happens. To upgrade a room version, use Element's "Upgrade room" UI — there is no script in this skill for room upgrades.

## EN/DE phrasing

Pass `--language de` (or set `LANGUAGE=de`) on either rater script to emit German messages. Both phrasings are baked into `_lib/rating.py`.
