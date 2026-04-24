from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from _patchlib import (
    MANIFEST_PATH,
    PATCH_MARKER,
    PROJECT_ROOT,
    backup_path_for_sha,
    find_patch_target,
    load_manifest,
    looks_patched,
    openclaw_version,
    read_package_version,
    read_source_sha,
    render_patched_text,
    save_manifest,
    sha256_text,
    syntax_check_js,
    unified_diff,
    verify_install,
    write_backup_if_missing,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Apply the OpenClaw history spillover patch.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the diff but do not modify the target file')
    parser.add_argument('--force', action='store_true',
                        help='Re-apply even if target is already patched; preserves existing backup')
    args = parser.parse_args()

    status = verify_install()
    if status.status == 'patched':
        print(f'already patched: {status.target}')
        return 0
    if status.status == 'bundle-symbols-missing':
        raise SystemExit(
            f'cannot apply: {status.message}. '
            f'Upstream OpenClaw may have been updated in an incompatible way.'
        )

    target = status.target
    before = target.read_text()
    currently_patched = looks_patched(before)

    # Drift / unmanaged / moved-target / partial patch: only re-apply under --force,
    # and never overwrite a pristine backup with post-drift content.
    if currently_patched and not args.force:
        raise SystemExit(
            f'target appears patched but in state "{status.status}" '
            f'(not a clean match for this version). '
            f'Run revert first, or pass --force to re-apply without updating the backup.'
        )

    after = render_patched_text(before)
    if before == after:
        print(f'no changes needed: {target}')
        return 0

    syntax_check_js(after)

    diff = unified_diff(before, after, str(target), str(target))
    if args.dry_run:
        print(diff)
        return 0

    # Backup strategy:
    #   - Clean apply: snapshot current file (the pristine pre-patch content).
    #   - Force re-apply: keep existing manifest backup if it still exists; otherwise
    #     content-address what we have, but flag it so revert knows it may not be pristine.
    existing_manifest = load_manifest()
    if currently_patched and existing_manifest:
        existing_backup = Path(existing_manifest.get('backupPath', ''))
        if existing_backup.exists():
            backup = existing_backup
            backup_pristine = True
        else:
            backup = write_backup_if_missing(before)
            backup_pristine = False
    else:
        backup = write_backup_if_missing(before)
        backup_pristine = True

    target.write_text(after)

    pre_sha = sha256_text(backup.read_text()) if backup_pristine else sha256_text(before)
    manifest = {
        'projectRoot': str(PROJECT_ROOT),
        'projectVersion': read_package_version(),
        'sourceSha256': read_source_sha(),
        'appliedAt': datetime.now(timezone.utc).isoformat(),
        'openclawVersion': openclaw_version(),
        'targetPath': str(target),
        'targetFile': target.name,
        'preSha256': pre_sha,
        'postSha256': sha256_text(after),
        'backupPath': str(backup),
        'backupPristine': backup_pristine,
        'patchMarker': PATCH_MARKER,
        'manifestPath': str(MANIFEST_PATH),
    }
    save_manifest(manifest)
    print(f'patched {target}')
    print(f'backup: {backup}')
    if not backup_pristine:
        print('WARNING: backup reflects the pre-re-apply (possibly drifted) state, '
              'not a clean pristine file. revert will restore what was there before '
              'this apply, not the original unpatched bundle.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
