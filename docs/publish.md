# Publishing notes

## Current publish flow

This repo is published through GitHub using normal git/gh credentials available in the host environment.

## Security posture

- install/apply/verify/revert code paths do not make network calls
- patch state is recorded locally in the OpenClaw install under `.openclaw-history-spillover/installed.json`
- backups use content-addressed filenames based on the pre-patch SHA-256
- release archives should be published as release assets, not kept in git history

## Fast verification after install

```bash
npm test
npm run apply:patch -- --dry-run
npm run apply:patch
npm run verify:patch
```

## Revert

```bash
npm run revert:patch
```

## Suggested release process

1. run tests
2. apply or verify against a target install
3. rebuild `source.zip`
4. attach `source.zip` to a GitHub release
5. keep backup/state files out of git history
