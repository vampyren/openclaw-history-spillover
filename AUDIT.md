# AUDIT

## What this project changes

This project patches one installed OpenClaw distribution file at runtime:

- `.../openclaw/dist/chat-*.js`

The patch adds oversized-history spillover helpers and replaces the oversized history path so that very large history entries are written to `history-oversize/*.json` instead of being silently reduced to a blind placeholder.

## Safety properties

- no network calls in apply/verify/revert scripts
- no shelling out from apply/verify/revert scripts
- backups are content-addressed by SHA-256 of the pre-patch file
- install metadata is written to `.openclaw-history-spillover/installed.json`
- spillover files are written atomically via temp file + rename
- spillover directory/file permissions are tightened to 0700/0600
- spillover write failure falls back to the original omitted placeholder behavior

## Verification model

- `apply` resolves the current hashed `chat-*.js` target dynamically
- `verify` reports one of: `patched`, `reverted`, `unpatched`, `patched-unmanaged`, `patched-drifted`, `changed`, `moved-target`
- `revert` restores the recorded backup file for the install managed by `apply`

## Reviewed risk areas

- dynamic target resolution across OpenClaw updates
- idempotent apply behavior
- secret-bearing oversized tool output written to disk
- repo publishing hygiene (no raw session backups in public history)
