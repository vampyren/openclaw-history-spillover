# Design: durable chat history spillover

## Problem

OpenClaw replaces oversized chat history entries with a placeholder such as:

`[chat.history omitted: message too large]`

That keeps the UI responsive, but it makes the original content hard to recover from normal history views.

## Goal

Preserve oversized entries durably without letting them bloat chat history payloads.

## Desired behavior

When a message exceeds the chat history byte budget:

1. Persist the full original payload to a spillover artifact file.
2. Replace the in-history item with a compact stub.
3. Include enough metadata in the stub to make recovery easy.
4. Keep raw session data durable on disk.

## Stub contents

The compact replacement should include:

- reason (`message too large`)
- original byte size
- spillover file path/reference
- preview snippet

## Spillover artifact

Each oversized message is written as JSON and includes:

- creation timestamp
- session id
- transcript path
- original byte length
- original message payload

## Initial patch target

Prototype patch target:

- `/usr/lib/node_modules/openclaw/dist/chat-xN4niR21.js`

The current insertion point is the oversized chat history replacement path near:

- `replaceOversizedChatHistoryMessages(...)`
- `buildOversizedHistoryPlaceholder(...)`

## Why this is better than a blind placeholder

Blind placeholder behavior prevents UI overload, but it sacrifices recoverability.

Spillover preserves both:

- **usability** — compact history remains loadable
- **durability** — full content survives on disk

## Future improvements

- Add Control UI links/buttons to open spillover artifacts
- Add retention policy and cleanup tooling
- Add compression for very large payloads
- Add config options for spillover thresholds and paths
- Upstream the feature into OpenClaw cleanly instead of patching built dist
