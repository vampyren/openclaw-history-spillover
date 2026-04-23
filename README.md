# openclaw-history-spillover

Prototype and patch workspace for durable OpenClaw chat history spillover.

## Goal

Prevent oversized chat/session history entries from disappearing behind placeholders by spilling full oversized payloads to artifact files and keeping compact references in history.

## Scope

- Backup current OpenClaw state before changes
- Patch oversized history handling
- Preserve full payloads on disk
- Keep UI history compact
- Add tests and docs

## Status

Work in progress.
