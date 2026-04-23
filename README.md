# openclaw-history-spillover

Durable spillover for oversized OpenClaw chat history entries.

## Why this exists

OpenClaw currently protects the UI by replacing oversized history entries with a placeholder such as:

- `[chat.history omitted: message too large]`

That avoids payload blowups, but it can hide the original content from normal history views. This project implements a safer behavior:

- persist the full oversized entry to a file on disk
- keep a compact stub in history
- include byte size, preview text, and spillover file path in the stub

## Status

Prototype implemented and tested locally.

## Features

- Spill oversized history entries to `history-oversize/*.json`
- Keep a readable compact marker in history
- Preserve original payloads on disk
- Provide a reusable spillover module for testing and refinement
- Include local patch/apply/revert scripts and automated tests

## Project structure

- `src/spillover.js` — reusable spillover logic
- `tests/spillover.test.mjs` — automated tests
- `docs/design.md` — design notes
- `backups/` — original state snapshots taken before patching

## Current live patch target

The current prototype patches the installed OpenClaw distribution file:

- `/usr/lib/node_modules/openclaw/dist/chat-xN4niR21.js`

## How it works

When a chat history message exceeds the byte threshold:

1. the original message is written to a JSON artifact file
2. the history item is replaced with a compact stub
3. the stub includes:
   - spill marker
   - original byte size
   - spillover file path
   - preview text

## Development

### Run tests

```bash
npm test
```

### Patch helper commands

```bash
npm run apply:patch
npm run verify:patch
npm run revert:patch
```

## Caveats

- This is currently a prototype patch against the installed dist file, not a polished upstream PR yet.
- The live system still needs one clean end-to-end verification run after patching.
- GitHub publishing depends on available auth from this environment.

## License

MIT
