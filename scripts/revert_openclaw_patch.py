from pathlib import Path
import shutil
backup = Path('/root/.openclaw/workspace/openclaw-history-spillover/backups/20260423-145050/chat-xN4niR21.js')
target = Path('/usr/lib/node_modules/openclaw/dist/chat-xN4niR21.js')
if not backup.exists():
    raise SystemExit(f'backup not found: {backup}')
shutil.copy2(backup, target)
print(f'restored {target} from {backup}')
