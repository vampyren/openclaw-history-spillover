# Design: durable chat history spillover

## Problem

OpenClaw currently replaces oversized chat history entries with a placeholder such as `[chat.history omitted: message too large]`.

This protects the UI but loses direct access to the original payload from normal history views.

## Desired behavior

When a message exceeds the history byte budget:

1. Persist the full original payload to a spillover artifact file.
2. Replace the in-history item with a compact stub.
3. The stub should include:
   - reason
   - original size
   - artifact path/reference
   - short preview
4. Keep raw session data durable on disk.

## Initial patch target

Patch the OpenClaw chat history sanitization/oversize replacement path in the installed distribution first, then backfill cleaner upstream integration paths.
