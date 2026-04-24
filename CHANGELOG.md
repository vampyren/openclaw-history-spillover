# Changelog

## 0.3.0

### Patch pipeline safety

- **Breaking behavior change** for the installed bundle: the `logGateway`
  plumbing in the injected code has been removed (it was never used). Existing
  0.2.0 installs will report status `patched-drifted` after upgrading. To
  migrate: run `npm run revert:patch` then `npm run apply:patch`.
- `apply` now refuses to re-apply on top of an already-patched-but-drifted
  target without `--force`. This closes a bug where a forced re-apply would
  overwrite the content-addressed backup with a non-pristine snapshot,
  silently breaking `revert`.
- `revert` now verifies: backup SHA matches recorded `preSha256`, current
  target state is as expected (or `--force`), and the restored file actually
  matches `preSha256` after the write. Refuses to restore a non-pristine
  backup without `--force`.
- `apply` runs `node --check` on the rendered patched file before writing, so
  syntax errors in the patch pipeline are caught at apply time rather than
  at OpenClaw load time.
- New verify status `bundle-symbols-missing` reports when upstream OpenClaw
  has renamed or removed a symbol the injected code depends on.

### State directory moved

- Manifest + backups moved from `/usr/lib/node_modules/openclaw/.openclaw-history-spillover/`
  to `/var/lib/openclaw-history-spillover/` so `npm update openclaw` cannot
  wipe them.
- New env var `OPENCLAW_HISTORY_SPILLOVER_STATE_DIR` for non-standard installs.
- Falls back to `$XDG_STATE_HOME/openclaw-history-spillover/` or
  `~/.local/state/openclaw-history-spillover/` when not running as root.

### Spillover module (`src/spillover.js`)

- New `serializeChatHistoryMessageForBytes()` helper returns `{text, byteLength}`
  so the spill path can avoid redundant `JSON.stringify` calls on large messages.
- `extractChatHistoryPreview` accepts an optional pre-serialized text argument.

### Tests

- Added `tests/test_patchlib.py` — 16 Python tests for the patch pipeline,
  using a synthetic bundle fixture. Covers target resolution, render
  idempotency, missing-anchor detection, missing-symbol detection, output
  JS syntax validity, and env-override state dir.
- JS tests now cover the new `serializeChatHistoryMessageForBytes` helper,
  the pre-serialized preview path, spillover dir permissions (0700), and
  the `maxSingleMessageBytes` validator's rejection of `Infinity` / negatives.

### CLI

- New `--force` flag on `apply` and `revert`.
- New `--dry-run` flag on `apply` (also exposed as `npm run apply:patch:dry-run`).
- `npm test` now runs both JS and Python suites.

## 0.2.0

- Dynamic patch-target resolution via content-marker matching (no more pinned
  `chat-xN4niR21.js` filename).
- Install manifest at `/usr/lib/node_modules/openclaw/.openclaw-history-spillover/installed.json`
  with pre/post SHA-256s, OpenClaw version, project version, timestamp.
- Content-addressed backups keyed by pre-patch SHA-256.
- Atomic spill-file write (tmp + rename), directory 0700, file 0600.
- Spillover write failure falls back to the original omitted-placeholder
  behavior instead of crashing.
- `jsonUtf8Bytes(undefined)` returns 0 instead of throwing.
- `maxSingleMessageBytes` validator: rejects non-finite and negative values.
- `extractChatHistoryPreview` truncates on Unicode code points (no lone
  surrogates on emoji-boundary cuts).
- Test harness tmp dirs cleaned up via `t.after()`.
- `engines.node: >=18` declared.
- AUDIT.md added.

## 0.1.0

- Initial prototype for oversized chat history spillover to file.
- Design docs and placeholder apply/revert scripts.
