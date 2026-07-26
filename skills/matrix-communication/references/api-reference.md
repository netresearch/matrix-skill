# Matrix Client-Server API Reference

Quick reference for Matrix API endpoints used by this skill.

## Authentication

All requests require Bearer token authentication:

```bash
curl -H "Authorization: Bearer $MATRIX_TOKEN" ...
```

## Base URL

```
https://matrix.org/_matrix/client/v3
```

## Endpoints

### Account

```bash
# Who am I?
GET /account/whoami

# Response:
{
  "user_id": "@user:matrix.org",
  "device_id": "ABCDEF",
  "is_guest": false
}
```

### Rooms

```bash
# List joined rooms
GET /joined_rooms

# Response:
{
  "joined_rooms": ["!room1:server", "!room2:server"]
}

# Resolve room alias to ID
GET /directory/room/%23alias:server

# Response:
{
  "room_id": "!abc:server",
  "servers": ["server"]
}

# Get room name
GET /rooms/{roomId}/state/m.room.name

# Response:
{
  "name": "Room Name"
}
```

### Room Management

```bash
# Create a room
POST /createRoom

# Body:
{
  "name": "Room Name",
  "preset": "private_chat",
  "room_alias_name": "localpart",
  "topic": "Optional topic",
  "invite": ["@user:server"]
}

# preset: private_chat (default) | public_chat | trusted_private_chat

# Response:
{
  "room_id": "!abc:server"
}

# Invite a user
POST /rooms/{roomId}/invite

# Body:
{
  "user_id": "@user:server"
}

# Response: {} on success

# Get power levels (state key is the empty string, hence the trailing slash)
GET /rooms/{roomId}/state/m.room.power_levels/

# Response (abridged):
{
  "users": {"@admin:server": 100},
  "users_default": 0,
  "events": {...},
  "state_default": 50,
  "ban": 50, "kick": 50, "redact": 50, "invite": 0
}

# Set power levels — PUT replaces the ENTIRE state event, no server-side
# merge. Always GET first, mutate the "users" dict, then PUT the whole
# object back, or every other key (state_default, ban/kick/redact/invite,
# other users' levels) gets wiped.
PUT /rooms/{roomId}/state/m.room.power_levels/

# The acting user's own power level must be >= the level being granted
# and >= the target's current level, or the homeserver returns M_FORBIDDEN.

# On newer room versions the creator has implicit, permanent authority and
# must NOT appear in "users" — setting the creator's own level is rejected:
# {"error": "Creator user must not appear in content.users", ...}
```

### Messages

```bash
# Send message
PUT /rooms/{roomId}/send/m.room.message/{txnId}

# Body (plain text):
{
  "msgtype": "m.text",
  "body": "Hello!"
}

# Body (formatted):
{
  "msgtype": "m.text",
  "body": "**Hello!**",
  "format": "org.matrix.custom.html",
  "formatted_body": "<strong>Hello!</strong>"
}

# Response:
{
  "event_id": "$abc123"
}

# Read messages (via sync)
GET /sync?timeout=0&full_state=true&filter={...}

# Filter for specific room:
{
  "room": {
    "rooms": ["!roomId:server"],
    "timeline": {"limit": 10}
  }
}
```

## Message Types

| msgtype | Description |
|---------|-------------|
| `m.text` | Plain text message |
| `m.notice` | Bot/notification message |
| `m.emote` | Action message (/me) |
| `m.image` | Image attachment |
| `m.file` | File attachment |

### Reactions

```bash
# Send reaction
PUT /rooms/{roomId}/send/m.reaction/{txnId}

# Body:
{
  "m.relates_to": {
    "rel_type": "m.annotation",
    "event_id": "$target_event_id",
    "key": "👍"
  }
}
```

### Account Data

```bash
# Get account data (e.g., key backup passphrase info)
GET /user/{userId}/account_data/{type}

# Types: m.megolm_backup.v1, m.secret_storage.default_key, m.secret_storage.key.{keyId}
```

### Key Backup

```bash
# Get current backup version
GET /room_keys/version

# Response:
{
  "algorithm": "m.megolm_backup.v1.curve25519-aes-sha2",
  "auth_data": { ... },
  "count": 1234,
  "etag": "...",
  "version": "5"
}

# Get backed-up keys
GET /room_keys/keys?version={version}
```

## Event Types

| type | Description |
|------|-------------|
| `m.room.message` | Regular message |
| `m.room.encrypted` | E2EE encrypted message |
| `m.room.name` | Room name state |
| `m.room.topic` | Room topic state |
| `m.room.member` | Membership event |
| `m.reaction` | Reaction annotation (relates_to another event) |

## Error Codes

| errcode | Description |
|---------|-------------|
| `M_FORBIDDEN` | Access denied (not in room, no permission) |
| `M_UNKNOWN_TOKEN` | Invalid or expired access token |
| `M_NOT_FOUND` | Room/resource not found |
| `M_LIMIT_EXCEEDED` | Rate limited |
| `M_GUEST_ACCESS_FORBIDDEN` | Guest access not allowed |

## Rate Limits

Matrix homeservers typically enforce rate limits:
- ~10 messages per second per room
- ~100 requests per second per user

The skill scripts include basic error handling for rate limits.

## References

- [Matrix Client-Server API Spec](https://spec.matrix.org/latest/client-server-api/)
- [Matrix Room Versions](https://spec.matrix.org/latest/rooms/)
