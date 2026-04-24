from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from _patchlib import load_manifest, save_manifest, sha256_text, verify_install


def main() -> int:
    manifest = load_manifest()
    if manifest is None:
        raise SystemExit('no install manifest found; nothing to revert')
    target = Path(manifest['targetPath'])
    backup = Path(manifest['backupPath'])
    if not backup.exists():
        raise SystemExit(f'backup not found: {backup}')
    original = backup.read_text()
    target.write_text(original)
    manifest['revertedAt'] = datetime.now(timezone.utc).isoformat()
    manifest['currentSha256'] = sha256_text(original)
    save_manifest(manifest)
    result = verify_install()
    print(f'restored {target} from {backup}')
    print(f'status: {result.status}')
    return 0 if result.status == 'reverted' else 1


if __name__ == '__main__':
    raise SystemExit(main())
