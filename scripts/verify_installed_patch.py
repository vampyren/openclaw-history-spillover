from pathlib import Path
import sys
p = Path('/usr/lib/node_modules/openclaw/dist/chat-xN4niR21.js')
text = p.read_text()
needles = [
    'CHAT_HISTORY_SPILLOVER_DIRNAME = "history-oversize"',
    '[chat.history spilled: message too large]',
    'spilloverFile: filePath || void 0'
]
missing = [n for n in needles if n not in text]
if missing:
    print('missing patch markers:')
    for m in missing:
        print('-', m)
    sys.exit(1)
print('installed patch markers present')
