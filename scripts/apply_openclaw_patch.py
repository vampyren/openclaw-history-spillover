from __future__ import annotations

import argparse
from datetime import datetime, timezone

from _patchlib import (
    MANIFEST_PATH,
    PATCH_MARKER,
    PROJECT_ROOT,
    backup_path_for_sha,
    find_patch_target,
    openclaw_version,
    read_package_version,
    read_source_sha,
    render_patched_text,
    save_manifest,
    sha256_text,
    unified_diff,
    verify_install,
    write_backup_if_missing,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Apply the OpenClaw history spillover patch.')
    parser.add_argument('--dry-run', action='store_true', help='Print the diff but do not modify the target file')
    args = parser.parse_args()

    status = verify_install()
    if status.status == 'patched':
        print(f'already patched: {status.target}')
        return 0

    target = find_patch_target()
    before = target.read_text()
    after = render_patched_text(before)
    if before == after:
        print(f'no changes needed: {target}')
        return 0
    diff = unified_diff(before, after, str(target), str(target))
    if args.dry_run:
        print(diff)
        return 0

    backup = write_backup_if_missing(before)
    target.write_text(after)
    manifest = {
        'projectRoot': str(PROJECT_ROOT),
        'projectVersion': read_package_version(),
        'sourceSha256': read_source_sha(),
        'appliedAt': datetime.now(timezone.utc).isoformat(),
        'openclawVersion': openclaw_version(),
        'targetPath': str(target),
        'targetFile': target.name,
        'preSha256': sha256_text(before),
        'postSha256': sha256_text(after),
        'backupPath': str(backup),
        'patchMarker': PATCH_MARKER,
        'manifestPath': str(MANIFEST_PATH),
    }
    save_manifest(manifest)
    print(f'patched {target}')
    print(f'backup: {backup}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
