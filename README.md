# openclaw-history-spillover

Durable spillover for oversized OpenClaw chat history entries.

## Why this exists

OpenClaw currently protects the UI by replacing oversized chat-history entries
with a blind placeholder:

```
[chat.history omitted: message too large]
```

That avoids payload blowups, but the original content becomes unrecoverable
from normal history views. This project implements a safer behavior:

- persist the full oversized entry to a file on disk
- keep a compact stub in history with byte size, preview, and file path
- fall back to the original omitted-placeholder behavior if the write fails

## How it works

When a chat-history message exceeds the configured byte threshold:

1. the original message is written to a JSON artifact file next to the
   session transcript: `<transcript-dir>/history-oversize/<ts>-<sid>-<mid>.json`
2. the in-history item is replaced with a compact stub containing:
   - the spill marker `[chat.history spilled: message too large]`
   - `bytes=<original byte length>`
   - `file=<absolute path to spillover artifact>`
   - a truncated preview of the content
3. if the file write fails (permission, disk full, etc), the stub falls
   back to the original omitted placeholder — never worse than stock OpenClaw

Spillover artifacts are written atomically (tmp file + rename) with 0600
permissions; the spillover directory is 0700.

## Project structure

```
src/spillover.js              reusable ES module implementing the spillover logic
scripts/_patchlib.py          rendering + verification library for the installer
scripts/apply_openclaw_patch.py
scripts/verify_installed_patch.py
scripts/revert_openclaw_patch.py
tests/spillover.test.mjs      JS tests (node:test)
tests/test_patchlib.py        Python tests for the patch pipeline (unittest)
docs/design.md                design notes
AUDIT.md                      security-relevant properties and dependencies
```

## Installation

Requires: Node.js ≥ 18, Python ≥ 3.9, write access to the OpenClaw install
directory (typically root for global installs).

```bash
git clone https://github.com/vampyren/openclaw-history-spillover.git
cd openclaw-history-spillover
npm test              # sanity-check before touching anything

# Preview what would change
npm run apply:patch:dry-run

# Apply
sudo npm run apply:patch

# Verify
sudo npm run verify:patch
```

### Patch target resolution

The installer does **not** hard-code a filename. It resolves the patch target
dynamically by scanning `/usr/lib/node_modules/openclaw/dist/chat-*.js` for
files containing the anchor identifiers (`replaceOversizedChatHistoryMessages`,
`buildOversizedHistoryPlaceholder`, `CHAT_HISTORY_OVERSIZED_PLACEHOLDER`).
This means the installer keeps working across OpenClaw updates that
re-hash the bundle filename.

If zero or multiple candidates match, apply fails loudly.

### State directory

Manifest + backups live outside the OpenClaw install tree so `npm update openclaw`
cannot wipe them. Resolution order:

1. `$OPENCLAW_HISTORY_SPILLOVER_STATE_DIR` (env override)
2. `/var/lib/openclaw-history-spillover/` (default for root installs)
3. `$XDG_STATE_HOME/openclaw-history-spillover/`
4. `~/.local/state/openclaw-history-spillover/`

The manifest (`installed.json`) records:

- project version and source SHA-256
- OpenClaw version at apply time
- resolved target path and file name
- pre- and post-patch SHA-256 of the target
- path to the content-addressed backup
- `backupPristine` flag (false if recorded during a forced re-apply)

Backups are keyed by the SHA-256 of their content
(`backups/<sha256>.js`), so the same pristine backup is never duplicated.

## Commands

| Command | Purpose |
|---|---|
| `npm test` | Run JS + Python test suites |
| `npm run test:js` | Run only the JS tests |
| `npm run test:py` | Run only the Python patch-pipeline tests |
| `npm run apply:patch` | Apply the patch. Idempotent on clean matches. |
| `npm run apply:patch:dry-run` | Print the unified diff without writing |
| `npm run verify:patch` | Report current install status (exits 0 iff `patched`) |
| `npm run revert:patch` | Restore the pre-patch file from backup |

`apply` and `revert` both accept `--force` for recovery scenarios (see below).

## Verify statuses

`verify:patch` returns one of:

| Status | Meaning |
|---|---|
| `patched` | Current file SHA matches manifest.postSha256. Clean. |
| `reverted` | Current file SHA matches manifest.preSha256. Clean. |
| `unpatched` | No manifest, no patch markers. Fresh system. |
| `patched-unmanaged` | Patch markers present, no manifest. Install by another tool? |
| `patched-drifted` | Patch markers present but SHA differs from manifest. |
| `moved-target` | Resolved target path differs from manifest (likely after `npm update openclaw`). |
| `changed` | No patch markers, SHA differs from manifest.preSha256. |
| `bundle-symbols-missing` | Upstream OpenClaw renamed/removed a required symbol. |

Only `patched` returns exit code 0.

## Drift and re-apply

If `verify` reports `patched-drifted` or `patched-unmanaged` and you want to
re-apply over it, use `--force`. This **preserves** the existing manifest's
backup path rather than overwriting it with the drifted content. If no
existing backup is usable, the manifest marks `backupPristine: false` and
`revert` will subsequently refuse unless you also pass `--force`.

Normal recovery flow:

```bash
sudo npm run revert:patch
sudo npm run apply:patch
```

## Environment variables

- `OPENCLAW_HISTORY_SPILLOVER_STATE_DIR` — override the default state directory

## Caveats

- This is a runtime patch against the installed `dist/chat-*.js`, not an
  upstream PR. See `docs/design.md` for the intended long-term shape.
- Revert tooling depends on the content-addressed backup. If you delete the
  state directory, you must reinstall OpenClaw to restore a pristine bundle.
- See `AUDIT.md` for the list of OpenClaw bundle-internal symbols the injected
  code depends on.

## License

MIT
