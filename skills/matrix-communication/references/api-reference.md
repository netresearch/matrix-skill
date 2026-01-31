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

## Event Types

| type | Description |
|------|-------------|
| `m.room.message` | Regular message |
| `m.room.encrypted` | E2EE encrypted message |
| `m.room.name` | Room name state |
| `m.room.topic` | Room topic state |
| `m.room.member` | Membership event |

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
