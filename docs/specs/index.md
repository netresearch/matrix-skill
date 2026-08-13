# Specs

Design documents for this repository, in [OKF](https://okf.md/) form: one concept
per file, typed frontmatter, this index as the entry point.

## Design

- [Live room awareness for coding agents](2026-08-13-live-room-awareness.md) — A daemon that owns the E2EE store, streams decrypted room events to a JSONL log, and accepts send/react commands over a socket, so an agent can follow a room while it works.
