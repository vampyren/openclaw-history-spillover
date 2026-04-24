from __future__ import annotations

from _patchlib import verify_install


def main() -> int:
    result = verify_install()
    print(f'status: {result.status}')
    print(f'target: {result.target}')
    print(result.message)
    if result.manifest:
        print(f"openclawVersion: {result.manifest.get('openclawVersion')}")
        print(f"projectVersion:  {result.manifest.get('projectVersion')}")
        print(f"appliedAt:       {result.manifest.get('appliedAt')}")
        print(f"backupPath:      {result.manifest.get('backupPath')}")
        if result.manifest.get('backupPristine') is False:
            print('backupPristine:  false (recorded during a forced re-apply)')
    return 0 if result.status == 'patched' else 1


if __name__ == '__main__':
    raise SystemExit(main())
