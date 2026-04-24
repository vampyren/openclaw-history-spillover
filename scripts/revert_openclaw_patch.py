from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from _patchlib import load_manifest, save_manifest, sha256_text, verify_install


def main() -> int:
    parser = argparse.ArgumentParser(description='Revert the OpenClaw history spillover patch.')
    parser.add_argument('--force', action='store_true',
                        help='Proceed even if current target or backup SHAs are unexpected')
    args = parser.parse_args()

    manifest = load_manifest()
    if manifest is None:
        raise SystemExit('no install manifest found; nothing to revert')

    target = Path(manifest['targetPath'])
    backup = Path(manifest['backupPath'])
    pre_sha = manifest.get('preSha256')
    post_sha = manifest.get('postSha256')

    if not target.exists():
        raise SystemExit(f'target not found: {target}')
    if not backup.exists():
        raise SystemExit(f'backup not found: {backup}')

    # 1. Backup integrity
    backup_text = backup.read_text()
    backup_sha = sha256_text(backup_text)
    if pre_sha and backup_sha != pre_sha:
        msg = (f'backup SHA mismatch: expected {pre_sha}, got {backup_sha}. '
               f'Backup may be corrupted or swapped.')
        if not args.force:
            raise SystemExit(msg + ' Pass --force to revert anyway.')
        print(f'WARNING: {msg} Proceeding due to --force.')

    if manifest.get('backupPristine') is False and not args.force:
        raise SystemExit(
            'manifest flags backup as non-pristine (recorded during a forced re-apply). '
            'Reverting would restore a drifted state, not the original bundle. '
            'Pass --force to proceed anyway.'
        )

    # 2. Current target state
    current_text = target.read_text()
    current_sha = sha256_text(current_text)

    if pre_sha and current_sha == pre_sha:
        print(f'already reverted: {target}')
        return 0
    if post_sha and current_sha != post_sha and not args.force:
        raise SystemExit(
            f'target SHA differs from recorded postSha256 (current={current_sha}). '
            f'The file may have been modified since apply. Pass --force to revert anyway.'
        )

    # 3. Write revert
    target.write_text(backup_text)

    # 4. Verify the restore actually produced the expected content
    restored_sha = sha256_text(target.read_text())
    if pre_sha and restored_sha != pre_sha:
        raise SystemExit(
            f'revert verification failed: expected {pre_sha}, got {restored_sha}. '
            f'Target file may be in an inconsistent state.'
        )

    manifest['revertedAt'] = datetime.now(timezone.utc).isoformat()
    manifest['currentSha256'] = restored_sha
    save_manifest(manifest)

    result = verify_install()
    print(f'restored {target} from {backup}')
    print(f'status: {result.status}')
    return 0 if result.status == 'reverted' else 1


if __name__ == '__main__':
    raise SystemExit(main())
