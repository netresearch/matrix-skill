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

## Room-ID gotcha: newer rooms have no `:server` suffix

Room IDs are not always `!localpart:server`. Room version 12+ (hash-based IDs) can be just `!<hash>` with **no `:server` suffix** — e.g. `!vqqacuaPMN-dV0WHbz4ISOzOCws8HX0EWZ7UphUoiCQ`. Use the `room_id` **verbatim** as returned by `GET /v1/rooms` / `rooms.json`; never append a server part.

If you do append `:server` to such an id, the admin room endpoints (`GET /v1/rooms/{room_id}/messages`, `/state`, …) return an **empty result rather than a 404** — so it looks like "the room has no messages" when the room is fine and you simply addressed a non-existent id. Symptom: a messages fetch or `synapse-search.py` returns nothing for a room you *know* is active. Fix: copy the exact `room_id` from the snapshot, unmodified.

## Encryption note

The `synapse-search.py` script uses the same Client-Server search endpoint a regular Element client does. End-to-end-encrypted messages are encrypted on the homeserver, so the search index never sees plaintext. **Empty results ≠ no messages.**
