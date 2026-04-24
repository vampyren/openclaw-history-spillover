from __future__ import annotations

import difflib
import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

OPENCLAW_ROOT = Path('/usr/lib/node_modules/openclaw')
DIST_DIR = OPENCLAW_ROOT / 'dist'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON_PATH = PROJECT_ROOT / 'package.json'
SOURCE_PATH = PROJECT_ROOT / 'src' / 'spillover.js'


def _resolve_state_dir() -> Path:
    """Resolve the state directory, preferring explicit override > /var/lib > XDG > home.

    The state directory holds the install manifest and content-addressed backups.
    It is intentionally located OUTSIDE the openclaw install tree so that
    `npm update openclaw` cannot wipe it.
    """
    env = os.environ.get('OPENCLAW_HISTORY_SPILLOVER_STATE_DIR')
    if env:
        return Path(env)
    var_lib = Path('/var/lib/openclaw-history-spillover')
    if var_lib.exists() or os.access(var_lib.parent, os.W_OK):
        return var_lib
    xdg = os.environ.get('XDG_STATE_HOME')
    if xdg:
        return Path(xdg) / 'openclaw-history-spillover'
    return Path.home() / '.local' / 'state' / 'openclaw-history-spillover'


STATE_DIR = _resolve_state_dir()
BACKUPS_DIR = STATE_DIR / 'backups'
MANIFEST_PATH = STATE_DIR / 'installed.json'

PATCH_MARKER = 'const CHAT_HISTORY_SPILLOVER_DIRNAME = "history-oversize";'
PATCH_MARKER_ALT = "const CHAT_HISTORY_SPILLOVER_DIRNAME = 'history-oversize';"

# Identifiers the injected code depends on from the surrounding openclaw bundle.
# If openclaw renames any of these, the patch will apply cleanly (markers match)
# but the patched code will throw ReferenceError at runtime. Verified at apply
# and verify time so we fail fast instead of producing a broken install.
REQUIRED_BUNDLE_SYMBOLS = [
    'formatForLog',
    'CHAT_HISTORY_OVERSIZED_PLACEHOLDER',
    'CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES',
    'resolveTranscriptPath',
    'getMaxChatHistoryMessagesBytes',
    'capArrayByJsonBytes',
    'buildOversizedHistoryPlaceholder',
    'replaceOversizedChatHistoryMessages',
]

INJECTED_BLOCK = '''const CHAT_HISTORY_SPILLOVER_DIRNAME = "history-oversize";
const CHAT_HISTORY_PREVIEW_MAX_CHARS = 1200;
function serializeChatHistoryMessageForBytes(value) {
\ttry {
\t\tconst text = JSON.stringify(value);
\t\treturn {
\t\t\ttext,
\t\t\tbyteLength: text === void 0 ? 0 : Buffer.byteLength(text, "utf8")
\t\t};
\t} catch (err) {
\t\tconst fallback = JSON.stringify({ error: formatForLog(err), fallback: String(value) });
\t\treturn {
\t\t\ttext: fallback,
\t\t\tbyteLength: Buffer.byteLength(fallback, "utf8")
\t\t};
\t}
}
function safeSerializeForSpillover(value) {
\ttry {
\t\treturn JSON.stringify(value, null, 2);
\t} catch (err) {
\t\treturn JSON.stringify({ error: formatForLog(err), fallback: String(value) }, null, 2);
\t}
}
function extractChatHistoryPreview(message, maxChars = CHAT_HISTORY_PREVIEW_MAX_CHARS, serializedText) {
\ttry {
\t\tconst raw = typeof message === "string" ? message : (serializedText ?? safeSerializeForSpillover(message));
\t\tconst chars = Array.from(raw);
\t\treturn chars.length > maxChars ? `${chars.slice(0, maxChars).join("")}\n…[truncated preview]` : raw;
\t} catch {
\t\treturn "[preview unavailable]";
\t}
}
function sanitizeHistorySpilloverIdPart(value, fallback = "item") {
\tconst out = String(value ?? fallback).replace(/[^a-zA-Z0-9._-]+/g, "_");
\treturn out || fallback;
}
function ensureChatHistorySpilloverDir(baseDir) {
\tconst dir = path.join(baseDir, CHAT_HISTORY_SPILLOVER_DIRNAME);
\tfs.mkdirSync(dir, { recursive: true, mode: 448 });
\treturn dir;
}
function buildOversizedHistoryOmittedPlaceholder(message, options) {
\tconst now = options?.now ?? Date.now();
\treturn {
\t\trole: message && typeof message === "object" && typeof message.role === "string" ? message.role : "assistant",
\t\ttimestamp: message && typeof message === "object" && typeof message.timestamp === "number" ? message.timestamp : now,
\t\tcontent: [{
\t\t\ttype: "text",
\t\t\ttext: CHAT_HISTORY_OVERSIZED_PLACEHOLDER
\t\t}],
\t\t__openclaw: {
\t\t\ttruncated: true,
\t\t\treason: "oversized"
\t\t}
\t};
}
function persistOversizedHistoryMessage(message, options, serialized) {
\tconst now = options?.now ?? Date.now();
\tconst transcriptPath = options?.transcriptPath;
\tconst baseDir = transcriptPath ? path.dirname(transcriptPath) : path.join(process.cwd(), ".openclaw-history");
\tconst dir = ensureChatHistorySpilloverDir(baseDir);
\tconst ts = new Date(now).toISOString().replace(/[:.]/g, "-");
\tconst sessionPart = sanitizeHistorySpilloverIdPart(options?.sessionId || "session", "session");
\tconst idPart = sanitizeHistorySpilloverIdPart(options?.messageId || now, "message");
\tconst filePath = path.join(dir, `${ts}-${sessionPart}-${idPart}.json`);
\tconst bytes = serialized ? serialized.byteLength : serializeChatHistoryMessageForBytes(message).byteLength;
\tconst payload = {
\t\tcreatedAt: new Date(now).toISOString(),
\t\tsessionId: options?.sessionId ?? null,
\t\ttranscriptPath: transcriptPath || null,
\t\tbyteLength: bytes,
\t\tmessage
\t};
\tconst tmpPath = `${filePath}.tmp-${process.pid}-${now}`;
\tfs.writeFileSync(tmpPath, safeSerializeForSpillover(payload), { encoding: "utf8", mode: 384 });
\tfs.renameSync(tmpPath, filePath);
\treturn filePath;
}
function buildOversizedHistorySpilloverPlaceholder(message, options) {
\tconst now = options?.now ?? Date.now();
\tconst serialized = options?.serialized ?? serializeChatHistoryMessageForBytes(message);
\tconst preview = extractChatHistoryPreview(message, options?.previewMaxChars, serialized.text);
\tlet filePath;
\ttry {
\t\tfilePath = persistOversizedHistoryMessage(message, options, serialized);
\t} catch {
\t\treturn buildOversizedHistoryOmittedPlaceholder(message, { now });
\t}
\treturn {
\t\trole: message && typeof message === "object" && typeof message.role === "string" ? message.role : "assistant",
\t\ttimestamp: message && typeof message === "object" && typeof message.timestamp === "number" ? message.timestamp : now,
\t\tcontent: [{
\t\t\ttype: "text",
\t\t\ttext: `[chat.history spilled: message too large]\nbytes=${serialized.byteLength}${filePath ? `\nfile=${filePath}` : ""}\npreview:\n${preview}`
\t\t}],
\t\t__openclaw: {
\t\t\ttruncated: true,
\t\t\treason: "oversized",
\t\t\tspilloverFile: filePath || void 0,
\t\t\toriginalBytes: serialized.byteLength
\t\t}
\t};
}
'''

PLACEHOLDER_WRAPPER = '''function buildOversizedHistoryPlaceholder(message, options) {
\treturn buildOversizedHistorySpilloverPlaceholder(message, options);
}
'''

REPLACE_OVERSIZED_FUNCTION = '''function replaceOversizedChatHistoryMessages(params) {
\tconst { messages, maxSingleMessageBytes, transcriptPath, sessionId } = params;
\tif (typeof maxSingleMessageBytes !== "number" || !Number.isFinite(maxSingleMessageBytes) || maxSingleMessageBytes < 0) throw new TypeError("maxSingleMessageBytes must be a finite non-negative number");
\tif (!Array.isArray(messages) || messages.length === 0) return {
\t\tmessages: messages ?? [],
\t\treplacedCount: 0
\t};
\tlet replacedCount = 0;
\tconst next = messages.map((message, index) => {
\t\tconst serialized = serializeChatHistoryMessageForBytes(message);
\t\tif (serialized.byteLength <= maxSingleMessageBytes) return message;
\t\treplacedCount += 1;
\t\tconst replacement = buildOversizedHistoryPlaceholder(message, { transcriptPath, sessionId, messageId: index, serialized });
\t\tif (replacement?.__openclaw?.spilloverFile || replacement?.content?.[0]?.text === CHAT_HISTORY_OVERSIZED_PLACEHOLDER) return replacement;
\t\treturn buildOversizedHistoryOmittedPlaceholder(message);
\t});
\treturn {
\t\tmessages: replacedCount > 0 ? next : messages,
\t\treplacedCount
\t};
}
'''

HISTORY_CALL_BLOCK = '''\t\tconst maxHistoryBytes = getMaxChatHistoryMessagesBytes();
\t\tconst transcriptPath = resolveTranscriptPath({
\t\t\tsessionId,
\t\t\tstorePath,
\t\t\tsessionFile: entry?.sessionFile,
\t\t\tagentId: entry?.agentId
\t\t});
\t\tconst replaced = replaceOversizedChatHistoryMessages({
\t\t\tmessages: normalized,
\t\t\tmaxSingleMessageBytes: Math.min(CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES, maxHistoryBytes),
\t\t\ttranscriptPath,
\t\t\tsessionId
\t\t});
\t\tconst capped = capArrayByJsonBytes(replaced.messages, maxHistoryBytes).items;'''


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_package_version() -> str:
    return json.loads(PACKAGE_JSON_PATH.read_text())['version']


def read_source_sha() -> str:
    return sha256_text(SOURCE_PATH.read_text())


def load_manifest() -> Optional[dict]:
    if not MANIFEST_PATH.exists():
        return None
    return json.loads(MANIFEST_PATH.read_text())


def save_manifest(data: dict) -> None:
    """Write manifest atomically with 0600 perms; state dir is 0700."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STATE_DIR, 0o700)
    except PermissionError:
        pass
    text = json.dumps(data, indent=2) + '\n'
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), prefix='.manifest-', suffix='.json')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.replace(tmp, MANIFEST_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def openclaw_version() -> str:
    package_json = OPENCLAW_ROOT / 'package.json'
    if not package_json.exists():
        return 'unknown'
    return json.loads(package_json.read_text()).get('version', 'unknown')


def find_patch_target(dist_dir: Optional[Path] = None) -> Path:
    dist = dist_dir if dist_dir is not None else DIST_DIR
    candidates = sorted(glob.glob(str(dist / 'chat-*.js')))
    matches = []
    for raw in candidates:
        p = Path(raw)
        text = p.read_text()
        if ('replaceOversizedChatHistoryMessages' in text
                and 'buildOversizedHistoryPlaceholder' in text
                and 'CHAT_HISTORY_OVERSIZED_PLACEHOLDER' in text):
            matches.append(p)
    if len(matches) != 1:
        raise SystemExit(f'expected 1 patch target, found {len(matches)}: {matches}')
    return matches[0]


def missing_bundle_symbols(text: str) -> List[str]:
    """Return required bundle-internal symbols not present in `text`."""
    return [s for s in REQUIRED_BUNDLE_SYMBOLS if s not in text]


def replace_span(text: str, start_marker: str, end_marker: str, replacement: str,
                 label: str, include_end: bool = False) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f'failed to find start marker for {label}')
    end = text.find(end_marker, start)
    if end == -1:
        raise SystemExit(f'failed to find end marker for {label}')
    if include_end:
        end += len(end_marker)
    return text[:start] + replacement + text[end:]


def render_patched_text(original: str) -> str:
    missing = missing_bundle_symbols(original)
    if missing:
        raise SystemExit(
            'target bundle is missing required symbols: '
            + ', '.join(missing)
            + '. OpenClaw may have been updated in an incompatible way.'
        )
    text = replace_span(
        original,
        'let chatHistoryPlaceholderEmitCount = 0;\n',
        'const CHANNEL_AGNOSTIC_SESSION_SCOPES = new Set([',
        'let chatHistoryPlaceholderEmitCount = 0;\n' + INJECTED_BLOCK + '\n',
        'helper injection'
    )
    text = replace_span(
        text,
        'function buildOversizedHistoryPlaceholder(',
        'function replaceOversizedChatHistoryMessages(params) {',
        PLACEHOLDER_WRAPPER,
        'placeholder wrapper'
    )
    text = replace_span(
        text,
        'function replaceOversizedChatHistoryMessages(params) {',
        'function enforceChatHistoryFinalBudget(params) {',
        REPLACE_OVERSIZED_FUNCTION,
        'replace oversized function'
    )
    text = replace_span(
        text,
        '\t\tconst maxHistoryBytes = getMaxChatHistoryMessagesBytes();',
        '\t\tconst capped = capArrayByJsonBytes(replaced.messages, maxHistoryBytes).items;',
        HISTORY_CALL_BLOCK,
        'history call block',
        include_end=True
    )
    if PATCH_MARKER not in text or 'spilloverFile: filePath || void 0' not in text:
        raise SystemExit('patched text missing expected markers after render')
    for fn in ('buildOversizedHistorySpilloverPlaceholder',
               'buildOversizedHistoryOmittedPlaceholder',
               'persistOversizedHistoryMessage',
               'ensureChatHistorySpilloverDir',
               'serializeChatHistoryMessageForBytes'):
        if fn not in text:
            raise SystemExit(f'patched text missing expected function: {fn}')
    return text


def syntax_check_js(text: str) -> None:
    """Best-effort JS syntax check via `node --check`. No-op if node is missing."""
    node = shutil.which('node')
    if not node:
        return
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        result = subprocess.run(
            [node, '--check', tmp],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise SystemExit(f'rendered patch is not valid JS:\n{result.stderr.strip()}')
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def looks_patched(text: str) -> bool:
    return PATCH_MARKER in text or PATCH_MARKER_ALT in text


def backup_path_for_sha(sha: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(BACKUPS_DIR, 0o700)
    except PermissionError:
        pass
    return BACKUPS_DIR / f'{sha}.js'


def write_backup_if_missing(target_text: str) -> Path:
    sha = sha256_text(target_text)
    backup_path = backup_path_for_sha(sha)
    if not backup_path.exists():
        backup_path.write_text(target_text)
        os.chmod(backup_path, 0o600)
    return backup_path


def unified_diff(before: str, after: str, fromfile: str, tofile: str) -> str:
    return ''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True),
        fromfile=fromfile, tofile=tofile
    ))


@dataclass
class VerificationResult:
    status: str
    target: Path
    message: str
    manifest: Optional[dict]


def verify_install() -> VerificationResult:
    """Return the current patch status.

    Status values:
      patched                 target matches manifest.postSha256 (clean patched)
      reverted                target matches manifest.preSha256  (clean reverted)
      unpatched               no manifest, no patch markers
      patched-unmanaged       patch markers present, no manifest
      patched-drifted         patch markers present, SHA differs from manifest
      moved-target            resolved target path differs from manifest
      changed                 no patch markers, SHA differs from manifest.preSha256
      bundle-symbols-missing  required openclaw symbols absent from target
    """
    target = find_patch_target()
    current_text = target.read_text()
    current_sha = sha256_text(current_text)
    missing = missing_bundle_symbols(current_text)
    manifest = load_manifest()

    if missing and not looks_patched(current_text):
        # Pre-patch bundle lost required symbols; upstream breaking change.
        return VerificationResult(
            'bundle-symbols-missing', target,
            f'target bundle is missing required symbols: {", ".join(missing)}',
            manifest,
        )

    if manifest is None:
        if looks_patched(current_text):
            return VerificationResult(
                'patched-unmanaged', target,
                'target is patched but no install manifest exists', None
            )
        return VerificationResult('unpatched', target, 'target is not patched', None)

    if str(target) != manifest.get('targetPath'):
        return VerificationResult(
            'moved-target', target,
            'resolved target does not match manifest target path', manifest
        )
    if current_sha == manifest.get('postSha256'):
        return VerificationResult('patched', target, 'installed patch matches manifest', manifest)
    if current_sha == manifest.get('preSha256'):
        return VerificationResult('reverted', target, 'target matches recorded pre-patch content', manifest)
    if looks_patched(current_text):
        return VerificationResult(
            'patched-drifted', target,
            'target still looks patched but hash differs from manifest', manifest
        )
    return VerificationResult('changed', target, 'target differs from both pre/post manifest hashes', manifest)
