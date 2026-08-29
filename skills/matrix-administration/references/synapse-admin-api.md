# Synapse Admin API — endpoint reference

Endpoints used by this skill, mapped to the upstream documentation.

All endpoints are reached through `_lib/admin_http.py`'s `admin_request()` (paths under `/_synapse/admin`) or `client_request()` (paths under `/_matrix/client/v3`). Authentication is a Bearer token taken from `admin_token` (or, as a fallback, `access_token`).

Upstream docs: <https://element-hq.github.io/synapse/latest/usage/administration/admin_api/index.html>

## Rooms

| Endpoint | Used by | Notes |
|----------|---------|-------|
| `GET /v1/rooms?from=N&sort` | `synapse-fetch-rooms.py` | Paginated, follow `next_batch` until missing. |
| `GET /v1/rooms/{room_id}` | `synapse-fetch-rooms.py`, `synapse-biggest-rooms.py`, `synapse-migrate-room.py` | Returns `version`, `name`, `join_rules`, `encryption`. |
| `GET /v1/rooms/{room_id}/state` | `synapse-fetch-rooms.py` | All current state events. |
| `POST /v1/rooms/{room_id}/make_room_admin` | `synapse-make-admin.py`, `synapse-migrate-room.py` | Body: `{"user_id": "@..."}`. Requires another admin to still be present. |
| `POST /v1/join/{room_id}` | `synapse-join-room.py` | Body: `{"user_id": "@..."}`. |
| `GET /v1/rooms/{room_id}/messages?dir=b&limit=N` | (ad-hoc timeline reads) | Reads a room's timeline **without joining** — unlike the Client-Server `/messages` endpoint, which 403s for rooms the token's user isn't in. Returns `chunk[]`. `from` is **optional** here (the admin endpoint defaults it, unlike the CS endpoint); pass `from`/`to` only to paginate. |

## Users

| Endpoint | Used by | Notes |
|----------|---------|-------|
| `GET /v2/users/{user_id}` | `synapse-deactivate-user.py` | Profile + admin status. |
| `GET /v2/users/{user_id}/joined_rooms` | `synapse-deactivate-user.py` | Returns `joined_rooms` array. |
| `POST /v1/deactivate/{user_id}` | `synapse-deactivate-user.py` | Body `{"erase": true}` for GDPR removal of message bodies. |
| `POST /v1/users/{user_id}/login` | (ad-hoc token minting) | Returns `access_token` for that user **without their password**. Empty body `{}` mints a non-expiring token; `{"valid_until_ms": N}` bounds it. Generates **no device** — see below. Cannot be used to log in as yourself. Disabled under Matrix Authentication Service. |
| `GET /v2/users/{user_id}/devices` | (ad-hoc token diagnosis) | Lists the user's devices. Only device-bound tokens (an ordinary `/login`) appear here; a token minted by the endpoint above never does. |

## Statistics

| Endpoint | Used by | Notes |
|----------|---------|-------|
| `GET /v1/statistics/database/rooms` | `synapse-biggest-rooms.py` | Returns `rooms[].estimated_size`. |

## Client-Server v3 (used with the admin token)

The admin user must be a member of the target room for state writes.

| Endpoint | Used by | Notes |
|----------|---------|-------|
| `GET /rooms/{room_id}/state` | `synapse-migrate-room.py`, `synapse-room-member-flow.py` | All current state events. |
| `PUT /rooms/{room_id}/state/{event_type}/{state_key}` | `synapse-add-to-space.py`, `synapse-migrate-room.py` | Used for `m.space.child`, `m.room.join_rules`, `m.room.encryption`, `m.room.power_levels`. |
| `POST /rooms/{room_id}/join` | `synapse-migrate-room.py` | Joins the calling user. |
| `GET /rooms/{room_id}/context/{event_id}?filter=...&limit=1` | `synapse-room-member-flow.py` | Used to recover the previous state event a leave/kick replaced. |
| `POST /search` | `synapse-search.py` | Body: room-event search payload, paginated via `next_batch`. |

## Minting a token for automation, and what it is actually bound to

`POST /v1/users/{user_id}/login` gives a pipeline, cron job or script its own
credential: as a server admin you mint a token for any user without knowing
their password. Two constraints before reaching for it — **it is disabled when
Matrix Authentication Service integration is enabled** (mint a MAS *personal
session* through the MAS Admin API instead), and it refuses to log a user in as
themselves, so an admin cannot use it to mint extra tokens for their own account.

**The token is bound to the minting admin, not to the target account.** Upstream
is explicit: the token expires if *the admin* calls `/logout/all` from any of
their devices, and does **not** expire when the target user does the same. So
putting the credential on a dedicated account removes the target's sessions as a
failure mode — worth doing — but the admin who minted it remains one. Mint from
an account whose sessions are stable, and record who minted it, because that is
the person whose `/logout/all` will take the pipeline down. To retire a token
deliberately, call the ordinary `/logout` with it.

**It generates no device.** The token does not appear in the target's `/devices`
list and `whoami` returns no `device_id` for it. Upstream puts the intent no
higher than "in general the target user *should not* be able to tell they have
been logged in as" — so treat the guarantee as covering the device list, not as
invisibility: actions taken with the token are ordinary events in the rooms the
target is in. The practical consequence is a diagnosis that does not work: `GET /v2/users/{user_id}/devices` says nothing
about a token minted this way, and an empty or unchanged device list is not
evidence either way. That check applies only to device-bound tokens from an
ordinary `/login`.

**What does diagnose it, in one call and no writes:** `GET
/_matrix/client/v3/account/whoami` — a valid token answers `200` with the
`user_id` it belongs to, an invalid one `401 M_UNKNOWN_TOKEN`. That proves
validity and ownership, never admin rights; for those, probe an admin endpoint
such as `GET /v1/rooms?limit=1` separately. **Send the token under test
explicitly** — `admin_request()` resolves `config.get("admin_token") or
config["access_token"]`, so a probe run through the usual config answers for the
configured admin token and not for the token you are asking about, and it answers
`200` either way. Pass a config carrying only the minted token, or issue the
request by hand. A Netresearch scheduled job failed 17 consecutive nights on
`401 M_UNKNOWN_TOKEN` with no code change in four months; `whoami` on the stored
credential settled it immediately, while the device list had nothing to say.

## Room-ID gotcha: newer rooms have no `:server` suffix

Room IDs are not always `!localpart:server`. Room version 12+ (hash-based IDs) can be just `!<hash>` with **no `:server` suffix** — e.g. `!vqqacuaPMN-dV0WHbz4ISOzOCws8HX0EWZ7UphUoiCQ`. Use the `room_id` **verbatim** as returned by `GET /v1/rooms` / `rooms.json`; never append a server part.

If you do append `:server` to such an id, the admin room endpoints (`GET /v1/rooms/{room_id}/messages`, `/state`, …) return an **empty result rather than a 404** — so it looks like "the room has no messages" when the room is fine and you simply addressed a non-existent id. Symptom: a messages fetch or `synapse-search.py` returns nothing for a room you *know* is active. Fix: copy the exact `room_id` from the snapshot, unmodified.

## Encryption note

The `synapse-search.py` script uses the same Client-Server search endpoint a regular Element client does. End-to-end-encrypted messages are encrypted on the homeserver, so the search index never sees plaintext. **Empty results ≠ no messages.**
