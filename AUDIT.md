# AUDIT

This document is for reviewers of the project (including clawhub.ai reviewers)
and for future maintainers. It describes exactly what this project modifies,
what it depends on, and what safety properties it claims.

## What this project changes

At apply time, one file in the OpenClaw install tree is modified in place:

- `/usr/lib/node_modules/openclaw/dist/chat-*.js` (the hashed filename is
  resolved dynamically, see `scripts/_patchlib.py::find_patch_target`)

The patch inserts helper functions and replaces two existing functions plus
one call site. No other OpenClaw files are touched.

## Safety properties

Grep-verifiable in `scripts/`:

- No network calls from any install/verify/revert code path
  (`grep -nE 'urllib|requests|urlopen|socket|http\\.|fetch' scripts/` returns nothing)
- No shelling out except `node --check` against a temp file for syntax
  validation (`scripts/_patchlib.py::syntax_check_js`)
- Backups are content-addressed by SHA-256 of the pre-patch file
- Install manifest is written atomically (tmpfile + `os.replace`) with mode 0600
- Spillover files are written atomically (tmp + rename) with mode 0600; the
  spillover directory is 0700
- Spillover write failure falls back to the original OpenClaw omitted
  placeholder — the patched behavior is never worse than stock OpenClaw
- Patch application is idempotent on clean targets
- Re-apply on a drifted target is refused unless `--force`; with `--force`
  the pristine backup is preserved, not overwritten
- Revert verifies backup SHA, current target state, and the post-write
  restore result
- `node --check` runs on the rendered patch before it is written to disk

## OpenClaw bundle dependencies

The injected code references symbols that must exist in the target OpenClaw
bundle. These are verified at apply and verify time; if any are missing,
apply refuses and verify reports status `bundle-symbols-missing`.

| Symbol | Used for |
|---|---|
| `formatForLog` | Error formatting inside serialize-failure fallbacks |
| `CHAT_HISTORY_OVERSIZED_PLACEHOLDER` | Omitted-placeholder marker string (reused, not redefined) |
| `CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES` | Byte threshold for the spillover decision |
| `resolveTranscriptPath` | Resolves `transcriptPath` at the history call site |
| `getMaxChatHistoryMessagesBytes` | Overall history-payload budget |
| `capArrayByJsonBytes` | Downstream budget-enforcement helper |
| `buildOversizedHistoryPlaceholder` | Existing function replaced by the patch |
| `replaceOversizedChatHistoryMessages` | Existing function replaced by the patch |

If an OpenClaw release renames or removes any of these, the patch will
refuse to apply (rather than produce a broken install).

## Scope of changes in the target bundle

The patch performs four span replacements in the target file:

1. **Helper injection** between `let chatHistoryPlaceholderEmitCount = 0;`
   and `const CHANNEL_AGNOSTIC_SESSION_SCOPES = new Set([`
   (~9 new functions, ~130 lines)
2. **Placeholder wrapper** replacing the original
   `buildOversizedHistoryPlaceholder` body (~3 lines)
3. **`replaceOversizedChatHistoryMessages`** body (~20 lines)
4. **History call site** (~11 lines replacing ~5 lines)

## Verification model

- `apply` checks status via `verify_install()` before touching anything.
  Already-patched targets are a no-op.
- `verify_install()` returns one of eight status values documented in
  `scripts/_patchlib.py::verify_install` and `README.md`.
- Only `status == patched` is an exit-0 success for `verify:patch`.

## Install record (this install)

Populate this section after running `apply` by copying from
`<state-dir>/installed.json`. Reviewers and future-you use it to confirm
what was tested against what.

```
openclawVersion:  <to fill in>
projectVersion:   <to fill in>
targetFile:       <to fill in>
preSha256:        <to fill in>
postSha256:       <to fill in>
appliedAt:        <to fill in>
```

## Reviewed risk areas

- Dynamic target resolution across OpenClaw updates (covered by verify
  status `moved-target`)
- Idempotent apply behavior (covered by `tests/test_patchlib.py::test_is_idempotent`)
- Bundle-symbol compatibility (covered by
  `tests/test_patchlib.py::test_fails_when_required_symbol_missing`)
- Oversized tool output written to disk — may contain secrets. Files are
  0600 and live next to the session transcript, which already has the same
  sensitivity level.
- Repo publishing hygiene — `backups/` is `.gitignore`d; live installed
  artifacts never enter the repo.

## How to reproduce the verification

```bash
npm test
```

Both the JS module and the Python patch pipeline are covered. The Python
suite uses a synthetic OpenClaw bundle fixture in
`tests/test_patchlib.py::SYNTHETIC_BUNDLE`, which contains all the anchor
strings and bundle-internal symbols the real target must provide.

The test `test_output_is_valid_js` additionally runs `node --check` on the
rendered output, catching any syntax regressions in the patch pipeline.
